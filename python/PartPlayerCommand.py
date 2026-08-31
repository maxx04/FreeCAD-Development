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
from PySide6 import QtWidgets

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
                # PropertyLinkSub/XLinkSub-Form: [Objekt, [Sub-Namen...]]
                ref_obj, subs = val
                if ref_obj.Name in copy_map:
                    try:
                        setattr(obj, prop, [copy_map[ref_obj.Name], subs])
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


class PartPlayerTaskPanel:
    """Aufgabenfenster: zeigt den Namen des bearbeiteten Teils + einen "Schritt"-Knopf.
    Reine Referenzobjekte (z.B. eine LCS) werden beim Oeffnen einmalig komplett kopiert -
    die eigentliche Feature-Historie wird dagegen echt additiv aufgebaut: jeder Klick fuegt
    GENAU EINE neue, echte Feature (Sketch, Pad, Pocket, ...) zum Body hinzu. Startet bei
    nichts (nur Ursprung + Extras), das Original wird dabei nie angefasst."""

    def __init__(self, body):
        self.body = body
        self._features = _ordered_features(body)
        self._step = 0
        self._copy_map = {}  # Original-Objektname -> bereits erstellte Kopie

        self.temp_doc = App.newDocument(f"PartPlayer_{body.Label}")
        self.temp_body = self.temp_doc.addObject("PartDesign::Body", "TemporaerBody")
        self.temp_body.Label = f"Temporär: {body.Label}"
        self.temp_body.Placement = body.Placement

        # Alles, was NICHT zur Feature-Historie gehoert (z.B. eine LCS), einmalig komplett
        # kopieren ("alles kopieren kein Ausschluss" fuer solche Referenzobjekte) - was zur
        # Historie gehoert, kommt bewusst erst schrittweise dazu (siehe _add_one_feature).
        chain_names = _chain_related_names(self._features)
        extras = [m for m in body.Group if m.Name not in chain_names]
        App.Console.PrintMessage(
            f"FCProject PartPlayer DEBUG: {len(self._features)} Feature(s) in Kette, "
            f"{len(body.Group)} Body.Group-Mitglied(er) insgesamt, {len(extras)} Extra(s): "
            f"{[m.Label for m in extras]}\n"
        )
        for orig_extra in extras:
            # Ein LCS (Part::LocalCoordinateSystem) braucht ihre EIGENEN internen
            # Unterobjekte (X_Achse/Y_Achse/... als "role"-Features) rekursiv mitkopiert,
            # sonst meldet FreeCAD "doesn't contain feature with role X_Axis" - das ist eine
            # rein LOKALE Abhaengigkeit der LCS selbst, zieht nichts aus der Feature-Kette
            # mit. Alles andere (z.B. eine lose Referenz-Skizze) dagegen NICHT rekursiv
            # kopieren: die kann an einer Flaeche EINES Kettenobjekts haengen
            # (AttachmentSupport) - mit recursive=True wuerde das die ganze Kette
            # vorzeitig mitziehen (per Diagnose bestaetigt: 2 Extras fuehrten so zu 10
            # zusaetzlichen Objekten im Dokument). Ohne recursive bleibt so eine Kopie
            # einfach auf das ORIGINAL-Objekt verweisen - fuer reine Anzeige-Zwecke
            # unschaedlich, das Original wird nirgends veraendert.
            recursive = orig_extra.isDerivedFrom("App::LocalCoordinateSystem")
            extra_copies = self.temp_doc.copyObject([orig_extra], recursive)
            for c in extra_copies:
                if c.TypeId in _ORIGIN_LIKE_TYPES:
                    try:
                        self.temp_doc.removeObject(c.Name)
                    except Exception:
                        pass
                    continue
                if c.Label == orig_extra.Label:
                    self._copy_map[orig_extra.Name] = c
                self.temp_body.addObject(c)

        # Noch kein Tip gesetzt - Startzustand zeigt keine Feature-Geometrie, wie gewuenscht.
        self.temp_doc.recompute()
        try:
            Gui.getDocument(self.temp_doc.Name).ActiveView.fitAll()
        except Exception:
            pass

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("FCProject: Part Player")
        layout = QtWidgets.QVBoxLayout(self.form)

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

        self._update_progress_label()

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
                self.form, "FCProject",
                f"Feature „{target_feature.Label}“ konnte nicht kopiert werden: {str(e)}"
            )
            return

        self._step += 1
        self._update_progress_label()

    def _add_one_feature(self, target_feature):
        """Kopiert NUR das, was fuer target_feature NEU gebraucht wird (typischerweise die
        Feature selbst + ihre eigene Sketch, falls vorhanden) - alles bereits Kopierte (aus
        vorherigen Schritten oder den Extras) wird wiederverwendet statt erneut kopiert."""
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
            for orig, copy in zip(to_copy, new_copies):
                if copy.TypeId in _ORIGIN_LIKE_TYPES:
                    try:
                        self.temp_doc.removeObject(copy.Name)
                    except Exception:
                        pass
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

    def accept(self):
        Gui.Control.closeDialog()
        return True

    def reject(self):
        Gui.Control.closeDialog()
        return True

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Close.value)


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

        Gui.Control.showDialog(PartPlayerTaskPanel(body))

    def IsActive(self):
        sel = Gui.Selection.getSelection()
        return len(sel) == 1 and sel[0].isDerivedFrom('PartDesign::Body')


Gui.addCommand('FCProject_PartPlayer', PartPlayerCommand())
