# FCProject: PartPlayer - schrittweiser Feature-fuer-Feature-Nachbau eines PartDesign-Bodys
# in einem separaten, temporaeren Dokument (Nutzerwunsch 2026-08-31, angelehnt an das
# "Playback"-Werkzeug aus Creo). BEWUSST NICHT die native Rueckspul-Leiste
# (Strg+Umschalt+Z / Tip-Marker verschieben) - das wuerde den Bearbeitungszustand des
# ORIGINALS selbst veraendern. Stattdessen: reine Anzeige-Kopien in einem eigenen,
# separaten Dokument, das Original bleibt zu jedem Zeitpunkt komplett unangetastet.
#
# ECHT ADDITIV, VON 0 AUF (2026-08-31, nach mehreren Nutzer-Korrekturen): Beim Oeffnen wird
# NUR das kopiert, was NICHT zur eigentlichen Feature-Historie gehoert (z.B. eine LCS) -
# "alles kopieren kein Ausschluss" gilt fuer SOLCHE Referenzobjekte, sie werden einmalig
# komplett mitgenommen. Die eigentliche Konstruktionshistorie (Sketches, Pad, Pocket,
# Fillet, ...) wird dagegen bewusst NICHT vorab kopiert, sondern JEDER "Schritt"-Klick fuegt
# GENAU EINE neue Feature (+ das, was sie selbst noch braucht, z.B. ihre eigene Sketch) zum
# waehrend der ganzen Sitzung bestehen bleibenden Body hinzu - identischer Teil-Aufbau wie
# im Original, nur eben schrittweise sichtbar statt auf einen Schlag. Kein Verwerfen/
# Neuaufbauen des Dokuments pro Schritt mehr -> keine Kamera-Spruenge.
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtWidgets

# Nutzerwunsch (2026-08-31): KEIN Aufgabenfenster (Gui.Control/TaskDialog) - das blockiert die
# Aufgabenfenster-Spalte, die z.B. beim Selektieren von Objekten/Flaechen gebraucht wird.
# Stattdessen ein frei schwebendes, NICHT-modales Popup-Fenster (normales QDialog), das
# parallel zur normalen FreeCAD-Bedienung (Baum, 3D-Ansicht, Selektion) offen bleiben kann.
# Referenzen auf offene Fenster hier halten, sonst koennte Python sie einsammeln, bevor der
# Nutzer sie schliesst.
_open_players = []

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

# Objekte, die der Body beim Anlegen automatisch selbst mitbringt (eigener Ursprung/Datum-
# Ebenen) - eine mitkopierte Version davon vom ORIGINAL wird nie gebraucht (der temporaere
# Body hat schon seinen eigenen), sonst gaebe es einen zweiten, ueberzaehligen Ursprung.
_ORIGIN_LIKE_TYPES = ("App::Origin", "App::Line", "App::Plane", "App::Point")


def _ordered_features(body):
    """Liefert die Feature-Kette eines PartDesign-Bodys in ECHTER Erstellungsreihenfolge.

    Nicht einfach body.Group nehmen - dessen Reihenfolge muss nicht der tatsaechlichen
    Historien-Kette entsprechen. Stattdessen von body.Tip rueckwaerts ueber .BaseFeature
    laufen (das ist exakt die Kette, die auch die native Rueckspul-Leiste durchlaeuft),
    dann umdrehen."""
    chain = []
    seen = set()
    current = body.Tip
    while current is not None and current.Name not in seen:
        seen.add(current.Name)
        chain.append(current)
        current = getattr(current, "BaseFeature", None)
    chain.reverse()
    return chain


def _chain_related_names(features):
    """Alle Namen, die zur Feature-Historie gehoeren: die Features selbst UND alles, was
    sie (rekursiv ueber OutList) brauchen - z.B. ihre eigenen Sketches. Wichtig: eine Sketch
    hat selbst keine .BaseFeature und zaehlt deshalb NICHT als "Feature" - muss hier trotzdem
    ausgeschlossen werden, sonst wuerde sie faelschlich als "Extra"-Referenzobjekt vorab
    mitkopiert (siehe Fehler in einer frueheren Version - eine Sketch eines SPAETEREN,
    noch nicht dran gewesenen Features geriet so in die Vorab-Kopie und riss beim
    rekursiven Kopieren gleich die halbe restliche Kette mit)."""
    names = set()

    def visit(obj):
        if obj.Name in names:
            return
        names.add(obj.Name)
        for dep in obj.OutList:
            visit(dep)

    for f in features:
        visit(f)
    return names


def _redirect_links(obj, copy_map):
    """Biegt in allen Link-artigen Eigenschaften von obj Verweise auf ORIGINAL-Objekte auf
    die entsprechenden, bereits angelegten Kopien um (copy_map: Original-Name -> Kopie).

    Noetig, weil eine per copyObject(..., recursive=False) neu angelegte Kopie ihre eigenen
    Verknuepfungen (z.B. BaseFeature, Profile/Sketch-Referenz) noch auf die ORIGINALEN
    Objekte zeigen hat, nicht auf die in frueheren Schritten bereits erstellten Kopien -
    generische Eigenschafts-Introspektion statt Feature-Typ-spezifischem Sonderwissen."""
    # WICHTIG: nicht hasattr(x, "isDerivedFrom") als Duck-Typing-Check verwenden - eine
    # Sketch hat z.B. eine "Geometry"-Eigenschaft mit rohen Part.Geometry-Objekten
    # (Part.LineSegment usw.), die isDerivedFrom() zwar geerbt haben (FreeCAD-Basisklasse),
    # aber KEIN .Name - fuehrte zu 'Part.LineSegment' object has no attribute 'Name'. Nur
    # echte App::DocumentObject-Instanzen zaehlen als Objekt-Referenz.
    for prop in obj.PropertiesList:
        try:
            val = getattr(obj, prop)
        except Exception:
            continue
        if val is None:
            continue

        if isinstance(val, App.DocumentObject):
            if val.Name in copy_map:
                try:
                    setattr(obj, prop, copy_map[val.Name])
                except Exception:
                    pass
            continue

        if isinstance(val, (list, tuple)):
            if len(val) == 2 and isinstance(val[0], App.DocumentObject):
                # PropertyLinkSub/XLinkSub-Form (SINGULAR): [Objekt, [Sub-Namen...]]
                ref_obj, subs = val
                if ref_obj.Name in copy_map:
                    try:
                        setattr(obj, prop, [copy_map[ref_obj.Name], subs])
                    except Exception:
                        pass
                continue

            # PropertyLinkSubList-Form (MEHRZAHL, z.B. AttachmentSupport): eine Liste von
            # (Objekt, Sub-Namen)-TUPELN, nicht ein einzelnes [Objekt, Subs]-Paar - per
            # Diagnose bestaetigt: mit nur EINEM Eintrag hat val genau Laenge 1, nicht 2,
            # und das einzige Listenelement ist selbst ein Tupel statt eines DocumentObject -
            # ist beim obigen Laenge-2-Check und beim einfachen Objekt-Listen-Fall unten
            # durchgerutscht, AttachmentSupport zeigte deshalb dauerhaft auf die ueberzaehlige
            # Ursprungs-Kopie statt auf das Original/die Kopie umgebogen zu werden.
            if val and all(
                isinstance(item, (list, tuple)) and len(item) == 2
                and isinstance(item[0], App.DocumentObject)
                for item in val
            ):
                changed = False
                new_list = []
                for ref_obj, subs in val:
                    if ref_obj.Name in copy_map:
                        new_list.append((copy_map[ref_obj.Name], subs))
                        changed = True
                    else:
                        new_list.append((ref_obj, subs))
                if changed:
                    try:
                        setattr(obj, prop, new_list)
                    except Exception:
                        pass
                continue

            changed = False
            new_list = []
            for item in val:
                if isinstance(item, App.DocumentObject) and item.Name in copy_map:
                    new_list.append(copy_map[item.Name])
                    changed = True
                else:
                    new_list.append(item)
            if changed:
                try:
                    setattr(obj, prop, new_list)
                except Exception:
                    pass


class PartPlayerDialog(QtWidgets.QDialog):
    """Frei schwebendes, NICHT-modales Popup-Fenster (kein Aufgabenfenster!): zeigt den Namen
    des bearbeiteten Teils + einen "Schritt"-Knopf. Reine Referenzobjekte (z.B. eine LCS)
    werden beim Oeffnen einmalig komplett kopiert - die eigentliche Feature-Historie wird
    dagegen echt additiv aufgebaut: jeder Klick fuegt GENAU EINE neue, echte Feature (Sketch,
    Pad, Pocket, ...) zum Body hinzu. Startet bei nichts (nur Ursprung + Extras), das Original
    wird dabei nie angefasst."""

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"FCProject: Part Player – {body.Label}")
        # Nicht-modal: Baum/3D-Ansicht/Selektion bleiben bedienbar, waehrend das Fenster offen
        # ist (anders als ein modaler Dialog oder das Aufgabenfenster).
        self.setModal(False)
        self.body = body
        self._features = _ordered_features(body)
        self._step = 0
        self._copy_map = {}  # Original-Objektname -> bereits erstellte Kopie

        self.temp_doc = App.newDocument(f"PartPlayer_{body.Label}")
        self.temp_body = self.temp_doc.addObject("PartDesign::Body", "TemporaerBody")
        self.temp_body.Label = f"Temporär: {body.Label}"
        self.temp_body.Placement = body.Placement

        # ANMERKUNG (Nutzer 2026-08-31): im ORIGINAL haengt die LCS an der body-eigenen
        # Origin-XY-Ebene. Beim Kopieren entsteht dadurch eine ueberzaehlige zweite Kopie
        # dieser Ebene ("XY_Plane002") - der temporaere Body hat aber schon seine EIGENE.
        # _reconcile_origin_copies() biegt solche Duplikate stattdessen auf das
        # Gegenstueck im EIGENEN Ursprung des temporaeren Bodys um.

        # VORBEUGUNG (per Diagnose bestaetigt, 2026-08-31): der eigene OutList-Waelzer in
        # _add_one_feature() zieht sonst bei JEDEM Feature, dessen Sketch an einer
        # Original-Ursprungsebene haengt, die GESAMTE Ursprungsfamilie (7 Rollen-Objekte +
        # Origin-Container) als vermeintlich "neue Abhaengigkeit" mit rein. copy_map wird
        # deshalb schon HIER, vor jeder Kopie, mit der Zuordnung Original-Ursprung ->
        # eigener Ursprung des temporaeren Bodys vorbefuellt - visit() sieht diese Namen
        # dann als "bereits erledigt" an und stoppt dort.
        self._copy_map[body.Origin.Name] = self.temp_body.Origin
        temp_roles = {
            getattr(tf, "Role", None): tf for tf in self.temp_body.Origin.OriginFeatures
        }
        for of in body.Origin.OriginFeatures:
            match = temp_roles.get(getattr(of, "Role", None))
            if match is not None:
                self._copy_map[of.Name] = match

        # Alles, was NICHT zur Feature-Historie gehoert (z.B. eine LCS oder eine unbenutzte
        # Referenz-Skizze), wird zusaetzlich lautlos mitkopiert ("alles kopieren kein
        # Ausschluss" fuer solche Referenzobjekte) - ABER an der Stelle in der Reihenfolge, an
        # der sie tatsaechlich in body.Group stehen, nicht pauschal alle vorab am Anfang
        # (Nutzer-Korrektur 2026-08-31, "ich meine reihenfolge": eine Referenz-Skizze, die im
        # Original z.B. zwischen "LinearPattern" und "Pad003" liegt, muss auch bei diesem
        # Schritt dazukommen, nicht schon ganz am Anfang).
        chain_names = _chain_related_names(self._features)
        extras = [m for m in body.Group if m.Name not in chain_names]
        App.Console.PrintMessage(
            f"FCProject PartPlayer DEBUG: {len(self._features)} Feature(s) in Kette, "
            f"{len(body.Group)} Body.Group-Mitglied(er) insgesamt, {len(extras)} Extra(s): "
            f"{[m.Label for m in extras]}\n"
        )
        # Jedes Extra dem naechstfolgenden Kettenfeature in body.Group zuordnen - trailing
        # Extras (nach dem letzten Kettenfeature) werden dem LETZTEN Schritt angehaengt.
        chain_feature_names = {f.Name for f in self._features}
        extra_names_set = {e.Name for e in extras}
        self._extras_before = {f.Name: [] for f in self._features}
        pending = []
        for m in body.Group:
            if m.Name in chain_feature_names:
                self._extras_before[m.Name] = pending
                pending = []
            elif m.Name in extra_names_set:
                pending.append(m)
        if pending and self._features:
            self._extras_before[self._features[-1].Name].extend(pending)

        # Noch kein Tip gesetzt - Startzustand zeigt keine Feature-Geometrie, wie gewuenscht.
        self.temp_doc.recompute()
        try:
            Gui.getDocument(self.temp_doc.Name).ActiveView.fitAll()
        except Exception:
            pass

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("Bearbeitetes Teil:"))
        name_label = QtWidgets.QLabel(body.Label)
        name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(name_label)

        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setStyleSheet("color: #888;")
        layout.addWidget(self.progress_label)

        self.step_button = QtWidgets.QPushButton("Schritt")
        self.step_button.clicked.connect(self._on_step)
        layout.addWidget(self.step_button)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self._update_progress_label()

    def _copy_one_extra(self, orig_extra):
        """Kopiert EIN Referenzobjekt, das nicht Teil der PartDesign-Feature-Kette ist (z.B.
        eine LCS oder eine unbenutzte Referenz-Skizze) - lautlos, ohne eigenen "Schritt"-Klick
        zu verbrauchen, aber genau zu dem Zeitpunkt aufgerufen, an dem es laut body.Group auch
        im Original an der Reihe waere (siehe self._extras_before in __init__)."""
        # Ein LCS (Part::LocalCoordinateSystem) braucht ihre EIGENEN internen Unterobjekte
        # (X_Achse/Y_Achse/... als "role"-Features) rekursiv mitkopiert, sonst meldet FreeCAD
        # "doesn't contain feature with role X_Axis" - das ist eine rein LOKALE Abhaengigkeit
        # der LCS selbst, zieht nichts aus der Feature-Kette mit. Alles andere (z.B. eine lose
        # Referenz-Skizze) dagegen NICHT rekursiv kopieren: die kann an einer Flaeche EINES
        # Kettenobjekts haengen (AttachmentSupport) - mit recursive=True wuerde das die ganze
        # Kette vorzeitig mitziehen (per Diagnose bestaetigt: 2 Extras fuehrten so zu 10
        # zusaetzlichen Objekten im Dokument). Ohne recursive bleibt so eine Kopie einfach auf
        # das ORIGINAL-Objekt verweisen - fuer reine Anzeige-Zwecke unschaedlich, das Original
        # wird nirgends veraendert.
        recursive = orig_extra.isDerivedFrom("App::LocalCoordinateSystem")
        # return_all=True ist zwingend noetig (FreeCAD-Quellcode bestaetigt,
        # Document.cpp/DocumentPyImp.cpp): OHNE das liefert copyObject() bei recursive=True NUR
        # die explizit angeforderten Objekte zurueck (hier: nur die LCS selbst) - die rekursiv
        # mitkopierten Abhaengigkeiten (ihre 7 Rollen-Objekte + eine ueberzaehlige
        # Ursprungsebene) entstehen zwar trotzdem im Dokument, waren aber fuer unseren Code
        # unsichtbar und konnten so nie umgebogen/aufgeraeumt werden (per Diagnose bestaetigt:
        # copies enthielt nur 1 Element statt 9).
        extra_copies = self.temp_doc.copyObject([orig_extra], recursive, True)
        # Namen VOR dem moeglichen Loeschen in _reconcile_origin_copies() erfassen - siehe
        # Kommentar dort, sonst droht ein Zugriff auf ein bereits geloeschtes Objekt.
        extra_names = [c.Name for c in extra_copies]
        removed_names = self._reconcile_origin_copies(extra_copies)
        for c, c_name in zip(extra_copies, extra_names):
            if c_name in removed_names:
                continue
            if c.TypeId in _ORIGIN_LIKE_TYPES:
                # Geschuetzte eigene Rollen-Unterobjekte (z.B. die 7 Achsen/Ebenen einer LCS) -
                # bleiben im Dokument, werden aber (wie beim Body-eigenen Ursprung ueblich)
                # nicht als eigenes Body-Mitglied gefuehrt.
                continue
            if c.Label == orig_extra.Label:
                self._copy_map[orig_extra.Name] = c
            self.temp_body.addObject(c)

    def _reconcile_origin_copies(self, copies):
        """Ueberzaehlige Ursprungs-Duplikate (Achse/Ebene/Origin-Punkt), die als Nebenprodukt
        eines rekursiven Kopiervorgangs entstehen - z.B. weil ein kopiertes Referenzobjekt an
        einer Ursprungsebene DES ORIGINALS haengt (AttachmentSupport) -, sollen NICHT als
        zweiter, ueberzaehliger Ursprung im Dokument liegen bleiben: der temporaere Body hat
        schon seinen EIGENEN vollstaendigen Ursprung mit denselben sieben Rollen
        (X_Axis/Y_Axis/Z_Axis/XY_Plane/XZ_Plane/YZ_Plane/Origin-Punkt). Jedes so betroffene
        Duplikat wird ueber seine 'Role'-Eigenschaft dem Gegenstueck im temporaeren Body
        zugeordnet, alle Verweise darauf umgebogen und das Duplikat geloescht.

        WICHTIG: eigene, dedizierte Rollen-Unterobjekte EINES Objekts in derselben Kopie-Charge
        (z.B. die 7 Rollen-Objekte einer LCS, verlinkt ueber deren eigene OriginFeatures-Liste)
        sind davon ausgenommen - die gehoeren exklusiv zu diesem einen Objekt und duerfen nicht
        mit dem geteilten Body-Ursprung zusammengelegt werden, sonst bricht die LCS.

        Gibt die Namen der tatsaechlich geloeschten Duplikate zurueck."""
        protected = set()
        for c in copies:
            for item in getattr(c, "OriginFeatures", []) or []:
                protected.add(item.Name)

        temp_roles = {}
        for tf in self.temp_body.Origin.OriginFeatures:
            role = getattr(tf, "Role", None)
            if role:
                temp_roles[role] = tf

        # App::Origin-CONTAINER separat behandeln: der haengt intern untrennbar mit seinen
        # eigenen 6+1 Rollen-Kindern zusammen - FreeCAD loescht beim Entfernen des Containers
        # AUTOMATISCH auch alle seine Kinder mit (Kaskade, per Diagnose bestaetigt: ein Schritt
        # erzeugte 8 Ursprungs-Duplikate inkl. Container, nur der Container wurde von uns
        # explizit entfernt, alle 7 Kinder verschwanden trotzdem mit). Wuerden wir DANACH noch
        # versuchen, die (schon laengst kaskadiert geloeschten) Kinder einzeln ueber
        # removeObject()/Attributzugriff zu behandeln, kollidiert das mit dem laengst
        # verschwundenen Objekt -> "Cannot access attribute 'TypeId' of deleted object".
        containers = []
        to_remove = []
        for c in copies:
            if c.TypeId == "App::Origin" and c.Name not in protected:
                containers.append(c)
                continue
            if c.TypeId not in _ORIGIN_LIKE_TYPES or c.Name in protected:
                continue
            match = temp_roles.get(getattr(c, "Role", None))
            if match is not None:
                self._copy_map[c.Name] = match
            to_remove.append(c)

        removable = {c.Name for c in containers} | {c.Name for c in to_remove}
        for c in copies:
            if c.Name not in removable:
                _redirect_links(c, self._copy_map)

        # WICHTIG: Namen VOR dem Loeschen zwischenspeichern. Nach removeObject() zeigt die
        # Python-Referenz auf ein geloeschtes FreeCAD-Objekt - ein erneutes Lesen von .Name
        # (z.B. fuer removed_names) wuerde "Cannot access attribute 'Name' of deleted object"
        # auslösen (per Diagnose bestaetigt: genau dieser Fehler brach zuvor mitten in
        # _add_one_feature ab, noch bevor die frisch kopierte Feature dem Body zugeordnet
        # wurde - daher blieb sie lose am Dokument haengen).
        # Alle betroffenen Namen JETZT einsammeln, bevor irgendetwas geloescht wird - danach
        # koennte ein Zugriff auf .Name selbst schon auf ein (per Kaskade) verschwundenes
        # Objekt treffen.
        container_names = [c.Name for c in containers]
        to_remove_names = [c.Name for c in to_remove]

        removed_names = set()

        # Container ZUERST loeschen - raeumt die eigenen Kinder per Kaskade gleich mit weg.
        for name in container_names:
            try:
                self.temp_doc.removeObject(name)
                removed_names.add(name)
            except Exception:
                pass

        # Danach die einzelnen Rollen-Objekte - nur noch ueber den zwischengespeicherten
        # Namen (String) ansprechen, nie wieder die urspruengliche Python-Referenz `c`
        # beruehren, die durch die Container-Kaskade schon ungueltig geworden sein kann.
        for name in to_remove_names:
            if self.temp_doc.getObject(name) is None:
                removed_names.add(name)
                continue
            try:
                self.temp_doc.removeObject(name)
                removed_names.add(name)
            except Exception:
                pass
        return removed_names

    def _update_progress_label(self):
        total = len(self._features)
        if total == 0:
            self.progress_label.setText("Dieses Teil hat keine Features in der Historie.")
            self.step_button.setEnabled(False)
            return
        if self._step >= total:
            self.progress_label.setText(f"Fertig - alle {total} Feature(s) angezeigt.")
            self.step_button.setEnabled(False)
        else:
            next_feature = self._features[self._step]
            self.progress_label.setText(
                f"Schritt {self._step + 1} von {total}: nächstes Feature „{next_feature.Label}“"
            )

    def _on_step(self):
        if self._step >= len(self._features):
            return
        target_feature = self._features[self._step]

        try:
            self._add_one_feature(target_feature)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "FCProject",
                f"Feature „{target_feature.Label}“ konnte nicht kopiert werden: {str(e)}"
            )
            return

        self._step += 1
        self._update_progress_label()

    def _add_one_feature(self, target_feature):
        """Kopiert NUR das, was fuer target_feature NEU gebraucht wird (typischerweise die
        Feature selbst + ihre eigene Sketch, falls vorhanden) - alles bereits Kopierte (aus
        vorherigen Schritten oder den Extras) wird wiederverwendet statt erneut kopiert."""
        # Extras, die laut body.Group VOR diesem Feature an der Reihe waeren (z.B. eine LCS
        # oder eine unbenutzte Referenz-Skizze), zuerst lautlos mitkopieren - an der Stelle in
        # der Reihenfolge, an der sie im Original tatsaechlich stehen, nicht pauschal am Anfang.
        for orig_extra in self._extras_before.get(target_feature.Name, []):
            if orig_extra.Name not in self._copy_map:
                self._copy_one_extra(orig_extra)

        to_copy = []
        visited = set(self._copy_map.keys())

        def visit(obj):
            if obj.Name in visited:
                return
            visited.add(obj.Name)
            for dep in obj.OutList:
                visit(dep)
            to_copy.append(obj)

        visit(target_feature)

        if to_copy:
            new_copies = self.temp_doc.copyObject(to_copy, False)
            # Namen VOR dem moeglichen Loeschen in _reconcile_origin_copies() erfassen - siehe
            # Kommentar dort, sonst droht ein Zugriff auf ein bereits geloeschtes Objekt.
            new_copy_names = [c.Name for c in new_copies]
            removed_names = self._reconcile_origin_copies(new_copies)
            for orig, copy, copy_name in zip(to_copy, new_copies, new_copy_names):
                if copy_name in removed_names or copy.TypeId in _ORIGIN_LIKE_TYPES:
                    continue
                self._copy_map[orig.Name] = copy

            # Interne Verknuepfungen ALLER bisherigen Kopien auf die (jetzt vollstaendige)
            # Zuordnungstabelle umbiegen - die frisch kopierten koennen aufeinander oder auf
            # bereits vorhandene Extras/vorherige Schritte zeigen.
            for copy in self._copy_map.values():
                _redirect_links(copy, self._copy_map)

            for orig in to_copy:
                copy = self._copy_map.get(orig.Name)
                if copy is not None and copy not in self.temp_body.Group:
                    self.temp_body.addObject(copy)

        copied_target = self._copy_map[target_feature.Name]
        self.temp_body.Tip = copied_target
        self.temp_doc.recompute()

        # Sichtbarkeit: nur die aktuelle (letzte) Feature soll sichtbar sein, damit man den
        # aktuellen Baustand tatsaechlich sieht - alle vorherigen Schritte werden (wie beim
        # Original ueblich) ausgeblendet.
        self.temp_body.ViewObject.Visibility = True
        for member in self.temp_body.Group:
            try:
                member.ViewObject.Visibility = (member is copied_target)
            except Exception:
                pass

        try:
            Gui.getDocument(self.temp_doc.Name).ActiveView.fitAll()
        except Exception:
            pass

class PartPlayerCommand:
    """Startet den PartPlayer fuer den ausgewaehlten PartDesign-Body."""

    def GetResources(self):
        return {
            'Pixmap': os.path.join(ICON_DIR, 'part_player.svg'),
            'MenuText': 'FCProject: Part Player',
            'ToolTip': (
                'Baut den ausgewaehlten PartDesign-Body Feature fuer Feature in einem neuen, '
                'separaten Dokument nach - Schritt fuer Schritt per Knopf, beginnend bei '
                'nichts (nur Ursprung). Das Original wird dabei nie veraendert - bewusst '
                'KEINE native Rueckspul-Leiste (Strg+Umschalt+Z).'
            )
        }

    def Activated(self):
        main_win = Gui.getMainWindow()
        sel = Gui.Selection.getSelection()

        if len(sel) != 1 or not sel[0].isDerivedFrom('PartDesign::Body'):
            QtWidgets.QMessageBox.warning(
                main_win, "FCProject",
                "Bitte zuerst genau einen PartDesign-Body im Baum auswählen."
            )
            return

        body = sel[0]
        if body.Tip is None:
            QtWidgets.QMessageBox.warning(
                main_win, "FCProject",
                f"'{body.Label}' hat keine Features (kein Tip gesetzt)."
            )
            return

        dialog = PartPlayerDialog(body, main_win)
        # Nicht-modaler Popup statt Aufgabenfenster (Nutzerwunsch) - Referenz halten, sonst
        # koennte Python das Fenster einsammeln, solange es noch offen ist.
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        _open_players.append(dialog)
        dialog.finished.connect(lambda *_: _open_players.remove(dialog) if dialog in _open_players else None)
        dialog.show()

    def IsActive(self):
        sel = Gui.Selection.getSelection()
        return len(sel) == 1 and sel[0].isDerivedFrom('PartDesign::Body')


Gui.addCommand('FCProject_PartPlayer', PartPlayerCommand())
