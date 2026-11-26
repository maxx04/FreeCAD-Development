# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check of SyncBinder.py (2026-11-26): binder in a part that copies neighbour geometry as placed
in an assembly, without a DAG cycle.

Setup in a throwaway folder: part "teil" (Body with a pad), source part "quelle" (box), sub-assembly
"sub" (two boxes, revolute, BoxA grounded), assembly "bg" with the part (grounded), the source
(free placement) and "sub" as a FLEXIBLE sub-assembly held by a Fixed joint (mirrors). A normal
SubShapeBinder in the part points with Support + Context into "bg" - the DAG cycle of the
Steuerbox.

Checked: conversion removes every link from the part to the assembly and keeps the geometry;
geometry seen through the assembly lies exactly on the source; automatic update after the
assembly recomputes (source moved, part instance moved); new Sync-Binder on a mirror in the
nested sub-assembly follows a new solve; source deleted / instance deleted -> last shape stays
with a status message; binder deleted -> assembly recomputes cleanly; save + reload keeps the
Sync properties; no write loop.

Run inside FreeCAD with GUI (e.g. under Xvfb):
    <sandbox>/sandbox-tests/common/run-test.sh <freecad> tests/fc_sync_binder_check.py
Prints "RESULT: PASS" or "RESULT: FAIL".
"""
import os
import sys
import tempfile
import zipfile

import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
sys.path.insert(0, "/home/maxx/Dokumente/FreeCAD-Development/assembly-solver-sandbox/sandbox-tests/common")
import joint_test_utils as jtu  # noqa: E402
import SyncBinder  # noqa: E402

V = App.Vector


def check(label, ok, detail=""):
    print(f"{label}: {detail} -> {'OK' if ok else 'FEHLER'}")
    return ok


def dist(a, b):
    va = [v.Point for v in a.Vertexes]
    vb = [v.Point for v in b.Vertexes]
    if not va or len(va) != len(vb):
        return float("inf")
    return max(min((p - q).Length for q in vb) for p in va)


def pump():
    from PySide import QtCore
    for _ in range(5):
        QtCore.QCoreApplication.processEvents()


def links_in_file(path, target_file):
    with zipfile.ZipFile(path) as z:
        xml = z.read("Document.xml").decode("utf-8")
    return xml.count(f'file="{target_file}"')


def main():
    import JointObject

    ok = True
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("DuplicateLabels", True)
    SyncBinder.register()
    folder = os.path.join(tempfile.mkdtemp(prefix="fcsync"), "PROJ_SYNC")
    os.makedirs(folder)
    p = lambda n: os.path.join(folder, n)  # noqa: E731

    q = App.newDocument("quelle")
    src = q.addObject("Part::Box", "Box")
    src.Length, src.Width, src.Height = 12, 8, 4
    q.recompute()
    q.saveAs(p("quelle.FCStd"))

    t = App.newDocument("teil")
    body = t.addObject("PartDesign::Body", "Body")
    # eigene Placement des Bodys (der Link in der Baugruppe ersetzt sie) - deckte 2026-11-26 den
    # doppelt umgerechneten Context auf
    body.Placement = App.Placement(V(7, -3, 11), App.Rotation(V(1, 1, 0), 25))
    box = body.newObject("PartDesign::AdditiveBox", "Grundkoerper")
    box.Length, box.Width, box.Height = 80, 60, 10
    t.recompute()
    t.saveAs(p("teil.FCStd"))

    parts = App.newDocument("teile")
    for name in ("BoxA", "BoxB", "BoxC"):
        b = parts.addObject("Part::Box", name)
        b.Length, b.Width, b.Height = 20, 10, 10
    parts.recompute()
    parts.saveAs(p("teile.FCStd"))
    sdoc = App.newDocument("sub")
    sdoc.saveAs(p("sub.FCStd"))
    sub = sdoc.addObject("Assembly::AssemblyObject", "Assembly")
    la = sub.newObject("App::Link", "BoxA")
    la.LinkedObject = parts.getObject("BoxA")
    lb = sub.newObject("App::Link", "BoxB")
    lb.LinkedObject = parts.getObject("BoxB")
    lb.Placement.Base = V(30, 0, 0)
    sdoc.recompute()
    jtu.ground_object(la)
    rev = JointObject.JointTypes.index("Revolute")
    fixed = JointObject.JointTypes.index("Fixed")
    jtu.make_joint(sub, rev, la, lb, App.Placement(V(20, 5, 5), App.Rotation(V(0, 1, 0), 90)),
                   App.Placement(V(0, 5, 5), App.Rotation(V(0, 1, 0), 90)), "Face2", "Face1")
    sdoc.recompute()
    sub.solve()
    sdoc.save()

    a = App.newDocument("bg")
    a.saveAs(p("bg.FCStd"))
    asm = a.addObject("Assembly::AssemblyObject", "Assembly")
    lt = asm.newObject("App::Link", "Teil")
    lt.LinkedObject = body
    lt.Placement = App.Placement(V(5, 5, 0), App.Rotation(V(0, 0, 1), 15))
    lq = asm.newObject("App::Link", "Quelle")
    lq.LinkedObject = src
    lq.Placement = App.Placement(V(30, 20, 10), App.Rotation(V(0, 0, 1), 40))
    lc = asm.newObject("App::Link", "BoxC")
    lc.LinkedObject = parts.getObject("BoxC")
    lc.Placement.Base = V(0, 90, 0)
    a.recompute()
    jtu.ground_object(lt)
    jtu.ground_object(lc)
    sublink = asm.newObject("Assembly::AssemblyLink", "Sub")
    sublink.LinkedObject = sub
    sublink.Rigid = False
    a.recompute()
    mb = next(c for c in sublink.Group if c.TypeId == "App::Link" and c.Label == "BoxB")
    outer = jtu.make_joint(asm, fixed, lc, mb, App.Placement(V(0, 0, 10), App.Rotation(V(1, 0, 0), 30)),
                           App.Placement(), "Face6", "Face5")
    a.recompute()
    asm.solve()
    a.recompute()
    a.save()

    # 1. Normaler Binder mit Kreis (wie Binder_UNO in der Steuerbox)
    native = body.newObject("PartDesign::SubShapeBinder", "Binder")
    native.Label = "Binder_Quelle"
    native.Support = [(lq, ["Face6"])]
    native.Context = (asm, f"{lt.Name}.{native.Name}.")
    native.Relative = True
    t.recompute()
    t.save()
    ok &= check("Ausgangslage: Teil verweist auf Baugruppe (Kreis)", links_in_file(p("teil.FCStd"), "bg.FCStd") > 0,
                f"{links_in_file(p('teil.FCStd'), 'bg.FCStd')} Verweise")
    seen_native = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
    truth = Part.getShape(asm, "Quelle.Face6", needSubElement=True)
    print(f"   (normaler Binder durch die Baugruppe gesehen: {dist(seen_native, truth):.2e})")

    # 2. Umwandeln
    msg = SyncBinder.convert_native_binder(native)
    t.recompute()
    t.save()
    seen = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
    holder = SyncBinder.holder_of(native)
    print(f"   (BindMode {native.BindMode}, Context {native.Context}, Halter {holder.Name if holder else None} "
          f"in {holder.Document.Name if holder else None}, Support {[(o.Name, sub) for o, sub in native.Support]})")
    ok &= check("Umwandeln", SyncBinder.is_sync_binder(native) and native.BindMode == "Synchronized"
                and native.Context is None and not native.Relative
                and holder is not None and holder.Document is t
                and native.Support[0][0] is holder
                and links_in_file(p("teil.FCStd"), "bg.FCStd") == 0 and dist(seen, truth) < 1e-9,
                f"{msg}; Verweise Teil->Baugruppe {links_in_file(p('teil.FCStd'), 'bg.FCStd')}, "
                f"Lage {dist(seen, truth):.2e}, Label '{native.Label}'")

    # 3. Automatisch: Quelle verschoben, Baugruppe neu berechnet
    calls = []
    original_sync = SyncBinder.sync

    def counting_sync(binder, force=False):
        calls.append(binder.Name)
        return original_sync(binder, force)

    SyncBinder.sync = counting_sync
    lq.Placement = App.Placement(V(45, 25, 10), App.Rotation(V(0, 0, 1), 70))
    a.recompute()
    pump()
    truth = Part.getShape(asm, "Quelle.Face6", needSubElement=True)
    seen = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
    ok &= check("Quelle verschoben -> automatisch", dist(seen, truth) < 1e-9,
                f"Lage {dist(seen, truth):.2e}, Sync-Aufrufe {len(calls)}, Status '{native.SyncStatus}'")
    # Teil-Instanz verschoben (Erdung kurz loesen)
    calls.clear()
    jtu_ground = next(o for o in a.Objects if getattr(o, "ObjectToGround", None) == lt)
    a.removeObject(jtu_ground.Name)
    lt.Placement = App.Placement(V(-10, 0, 0), App.Rotation(V(0, 0, 1), -20))
    a.recompute()
    pump()
    jtu.ground_object(lt)
    a.recompute()
    pump()
    truth = Part.getShape(asm, "Quelle.Face6", needSubElement=True)
    seen = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
    ok &= check("Teil verschoben -> automatisch", dist(seen, truth) < 1e-9,
                f"Lage {dist(seen, truth):.2e}, Sync-Aufrufe {len(calls)}")
    calls.clear()
    a.recompute()
    pump()
    ok &= check("keine Schleife (unveraendert -> nichts geschrieben)", native.SyncStatus.startswith("aktualisiert")
                and len(calls) <= 2, f"Sync-Aufrufe {len(calls)}")
    SyncBinder.sync = original_sync

    # 4. Neuer Sync-Binder auf einen Spiegel in der flexiblen Unterbaugruppe
    nested = SyncBinder.create_sync_binder(asm, f"{lt.Name}.Grundkoerper.Face6", [f"{sublink.Name}.{mb.Name}.Face5"],
                                           label="Binder_Spiegel")
    t.recompute()
    path_n = f"{lt.Name}.{nested.Name}."
    truth_n = Part.getShape(asm, f"{sublink.Name}.{mb.Name}.Face5", needSubElement=True)
    ok &= check("neuer Sync-Binder (verschachtelt)", dist(Part.getShape(asm, path_n), truth_n) < 1e-9
                and nested.Synchronisiert, f"Lage {dist(Part.getShape(asm, path_n), truth_n):.2e}, Pfad '{nested.SyncPfad}'")
    proxy = getattr(nested.ViewObject, "Proxy", None)
    ok &= check("Baum-Icon des neuen Sync-Binders", nested.TypeId == "PartDesign::SubShapeBinderPython"
                and SyncBinder.is_sync_binder(nested) and isinstance(proxy, SyncBinder.SyncBinderViewProvider)
                and os.path.basename(proxy.getIcon()) in ("sync_binder.svg", "sync_binder_dark.svg"),
                f"{nested.TypeId}, Icon {proxy.getIcon() if hasattr(proxy, 'getIcon') else proxy}")
    outer.Placement1 = App.Placement(V(0, 0, 10), App.Rotation(V(1, 0, 0), 75))
    a.recompute()
    asm.solve()
    a.recompute()
    pump()
    truth_n2 = Part.getShape(asm, f"{sublink.Name}.{mb.Name}.Face5", needSubElement=True)
    ok &= check("verschachtelte Quelle neu geloest -> automatisch", dist(truth_n, truth_n2) > 1
                and dist(Part.getShape(asm, path_n), truth_n2) < 1e-9,
                f"Spiegel bewegt {dist(truth_n, truth_n2):.1f}, Binder {dist(Part.getShape(asm, path_n), truth_n2):.2e}")

    # 4a. Vier Kanten als Quelle: der Binder macht daraus wie gewohnt eine Flaeche (MakeFace)
    quelle_shape = Part.getShape(asm, "Quelle", needSubElement=False)
    face_src = quelle_shape.Faces[0]
    edge_paths = []
    for i, e in enumerate(quelle_shape.Edges, start=1):
        if any(e.isSame(fe) for fe in face_src.Edges):
            edge_paths.append(f"Quelle.Edge{i}")
    framed = SyncBinder.create_sync_binder(asm, f"{lt.Name}.Grundkoerper.Face6", edge_paths, label="Binder_Kanten")
    t.recompute()
    ok &= check("vier Kanten -> Flaeche (MakeFace)", len(framed.Shape.Faces) == 1 and len(framed.Shape.Edges) == 4,
                f"{len(edge_paths)} Kanten, Binder hat {len(framed.Shape.Faces)} Flaeche(n)")

    # 4c. Pfad-Bereinigung und Zielerkennung (2026-11-26, Arduino-STEP ohne Body als erstes Element)
    mapped = "Quelle.;Face14;:H92b,F;:H93b:8,F;:Ha25:12,F.Face6"
    ok &= check("Elementname aus dem Pfad entfernt",
                SyncBinder.normalize_element_path(mapped) == "Quelle.Face6"
                and SyncBinder.normalize_element_path("Quelle.Face6") == "Quelle.Face6",
                SyncBinder.normalize_element_path(mapped))
    target_path = f"{lt.Name}.Grundkoerper.Face6"
    t1 = SyncBinder.split_target_and_sources(asm, [target_path, mapped])
    t2 = SyncBinder.split_target_and_sources(asm, [mapped, target_path])
    ok &= check("Ziel erkannt, Quelle zuerst oder Ziel zuerst",
                t1 == (target_path, ["Quelle.Face6"]) and t2 == (target_path, ["Quelle.Face6"]), f"{t1} / {t2}")
    errors = []
    for case in ([mapped, "Quelle.Face5"], [target_path, f"{lt.Name}.Grundkoerper.Face5"][:1]):
        try:
            SyncBinder.split_target_and_sources(asm, case)
            errors.append("keine Meldung")
        except RuntimeError as exc:
            errors.append(str(exc)[:40])
    ok &= check("ohne Body-Ziel / zu wenig Elemente -> Meldung", all(e != "keine Meldung" for e in errors), "; ".join(errors))

    # 4d. Mappe: mehrere Quellen -> ein Halte-Objekt pro Quelle, Elemente als Kinder unter dem Binder
    mappe_sources = ["Quelle.Face6", f"{sublink.Name}.{mb.Name}.Face5"]
    mappe = SyncBinder.create_sync_binder(asm, target_path, [mapped, mappe_sources[1]], label="Binder_Mappe")
    t.recompute()
    pump()
    holders = SyncBinder.holders_of(mappe)
    path_f = f"{lt.Name}.{mappe.Name}."

    def covered(truths, seen_shape):
        return all(min(dist(tr, f) for f in seen_shape.Faces) < 1e-9 for tr in truths)

    truths_f = [Part.getShape(asm, x, needSubElement=True) for x in mappe_sources]
    seen_f = Part.getShape(asm, path_f)
    ok &= check("Mappe: ein Halte-Objekt pro Quelle", len(holders) == 2 and list(mappe.SyncQuellen) == mappe_sources
                and mappe.ClaimChildren and {o.Name for o, _ in mappe.Support} == {h.Name for h in holders}
                and all(h.Document is t for h in holders) and len(mappe.SyncHalter.split(",")) == 2,
                f"Halter {[h.Label for h in holders]}, Quellen {list(mappe.SyncQuellen)} (erwartet {mappe_sources}), "
                f"ClaimChildren {mappe.ClaimChildren}, Support {[o.Name for o, _ in mappe.Support]}, SyncHalter '{mappe.SyncHalter}'")
    ok &= check("Mappe: beide Elemente liegen auf den Quellen", len(seen_f.Faces) == 2 and covered(truths_f, seen_f),
                f"{len(seen_f.Faces)} Flaechen")
    support_before = [o.Name for o, _ in mappe.Support]
    writes = []
    original_status = SyncBinder._set_status
    SyncBinder._set_status = lambda b, text: (writes.append(b.Name), original_status(b, text))[1]
    a.recompute()
    pump()
    SyncBinder._set_status = original_status
    ok &= check("Mappe: keine Schleife (unveraendert -> nichts geschrieben)",
                [o.Name for o, _ in mappe.Support] == support_before and writes.count(mappe.Name) == 0,
                f"Schreibvorgaenge {writes.count(mappe.Name)}")
    lq.Placement = App.Placement(V(60, -5, 10), App.Rotation(V(0, 0, 1), 33))
    a.recompute()
    pump()
    truths_f2 = [Part.getShape(asm, x, needSubElement=True) for x in mappe_sources]
    seen_f2 = Part.getShape(asm, path_f)
    ok &= check("Mappe: folgt der verschobenen Quelle", dist(truths_f[0], truths_f2[0]) > 1 and covered(truths_f2, seen_f2),
                f"Quelle bewegt {dist(truths_f[0], truths_f2[0]):.1f}, {len(seen_f2.Faces)} Flaechen")
    holder_names = [h.Name for h in holders]
    t.removeObject(mappe.Name)
    t.recompute()
    pump()
    pump()
    ok &= check("Mappe geloescht (alle Halte-Objekte mit)", all(t.getObject(n) is None for n in holder_names),
                f"noch da: {[n for n in holder_names if t.getObject(n) is not None]}")

    # 4b. Unterbaugruppe starr und wieder flexibel: Pfad zum Spiegel muss weiter aufloesen
    for rigid in (True, False):
        sublink.Rigid = rigid
        a.recompute()
        asm.solve()
        a.recompute()
        pump()
        status, _ = SyncBinder.sync(nested)
        truth_r = Part.getShape(asm, f"{sublink.Name}.{mb.Name}.Face5", needSubElement=True)
        ok &= check(f"Unterbaugruppe {'starr' if rigid else 'flexibel'}",
                    "nicht gefunden" not in status and dist(Part.getShape(asm, path_n), truth_r) < 1e-9,
                    f"{status}, Lage {dist(Part.getShape(asm, path_n), truth_r):.2e}")

    # 5. Speichern + Neuladen des Teils
    t.save()
    keep = (native.SyncDatei, native.SyncObjekt, native.SyncPfad, list(native.SyncQuellen))
    App.closeDocument(t.Name)
    t = App.openDocument(p("teil.FCStd"))
    native = t.getObject("Binder")
    nested = t.getObject("SyncBinder")
    ok &= check("Neuladen", SyncBinder.is_sync_binder(native) and
                (native.SyncDatei, native.SyncObjekt, native.SyncPfad, list(native.SyncQuellen)) == keep
                and not native.Shape.isNull(), str(keep))

    # 5b. Teil nur teilweise geladen (wie beim Oeffnen nur der Baugruppe): vor dem Schreiben
    # vollstaendig nachladen, sonst speichert FreeCAD die neue Geometrie nicht.
    for d in list(App.listDocuments().values()):
        if d.FileName:
            d.save()
    for d in list(App.listDocuments()):
        App.closeDocument(d)
    pump()
    a = App.openDocument(p("bg.FCStd"))
    asm, lq, lt = a.getObject("Assembly"), a.getObject("Quelle"), a.getObject("Teil")
    t = next(d for d in App.listDocuments().values() if d.FileName.endswith("teil.FCStd"))
    was_partial = t.Partial
    lq.Placement = App.Placement(V(20, 30, 10), App.Rotation(V(0, 0, 1), 5))
    a.recompute()
    pump()
    t = next(d for d in App.listDocuments().values() if d.FileName.endswith("teil.FCStd"))
    native = t.getObject("Binder")
    nested = t.getObject("SyncBinder")
    t.save()
    expected = Part.getShape(asm, "Quelle.Face6", needSubElement=True)
    seen = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
    ok &= check("teilweise geladenes Teil", not t.Partial and dist(seen, expected) < 1e-9,
                f"beim Oeffnen teilweise: {was_partial}, danach teilweise: {t.Partial}, Lage {dist(seen, expected):.2e}")

    # 5c. Teil allein oeffnen: die Baugruppe wird (wie beim normalen Binder) mitgeladen und der
    # Binder sofort aktualisiert. Dazu die Quelle OHNE Synchronisierung verschieben und speichern.
    SyncBinder.unregister()
    lq.Placement = App.Placement(V(-8, 44, 10), App.Rotation(V(0, 0, 1), 120))
    a.recompute()
    a.save()
    holder_before = SyncBinder.holder_of(native).Shape.copy()
    for d in list(App.listDocuments()):
        App.closeDocument(d)
    pump()  # die Oberflaeche raeumt geschlossene Dokumente erst hier weg (sonst trifft es das neue)
    SyncBinder.register()
    App.openDocument(p("teil.FCStd"))
    pump()
    t = next(d for d in App.listDocuments().values() if d.FileName.endswith("teil.FCStd"))
    a = next((d for d in App.listDocuments().values() if d.FileName.endswith("bg.FCStd")), None)
    native = t.getObject("Binder")
    nested = t.getObject("SyncBinder")
    ok_open = a is not None
    if ok_open:
        asm, lq, lt = a.getObject("Assembly"), a.getObject("Quelle"), a.getObject("Teil")
        truth = Part.getShape(asm, "Quelle.Face6", needSubElement=True)
        seen = Part.getShape(asm, f"{lt.Name}.{native.Name}.")
        moved = dist(holder_before, SyncBinder.holder_of(native).Shape)
        ok_open = dist(seen, truth) < 1e-9 and moved > 1
    ok &= check("Teil allein geoeffnet -> Baugruppe mitgeladen", ok_open,
                f"Baugruppe offen: {a is not None}, Status '{native.SyncStatus}'"
                + (f", Lage {dist(seen, truth):.2e}, Kopie bewegt {moved:.1f}" if a is not None else ""))
    proxy2 = getattr(nested.ViewObject, "Proxy", None) if nested is not None else None
    ok &= check("Baum-Icon nach Speichern und Neuladen", nested is not None
                and isinstance(proxy2, SyncBinder.SyncBinderViewProvider),
                f"{nested.TypeId if nested is not None else None}, Proxy {type(proxy2).__name__}")
    if a is None:
        a = App.openDocument(p("bg.FCStd"))
        asm, lq, lt = a.getObject("Assembly"), a.getObject("Quelle"), a.getObject("Teil")

    # 6. Quelle geloescht -> letzte Form bleibt, Hinweis
    before = native.Shape.copy()
    a.removeObject(lq.Name)
    a.recompute()
    pump()
    ok &= check("Quelle geloescht", "Quelle nicht gefunden" in native.SyncStatus and dist(before, native.Shape) < 1e-12,
                native.SyncStatus)

    # 7. Binder geloescht -> Baugruppe rechnet sauber weiter
    t.removeObject(nested.Name)
    t.recompute()
    a.recompute()
    pump()
    pump()
    ok &= check("Binder geloescht (Halte-Objekt mit)", a.getObject(asm.Name).isValid()
                and t.getObject("SyncBinder") is None and t.getObject("SyncBinder_SyncQuelle") is None,
                f"Halte-Objekt noch da: {t.getObject('SyncBinder_SyncQuelle') is not None}")

    # 8. Teil-Instanz geloescht -> Hinweis, Form bleibt
    before = native.Shape.copy()
    for o in list(a.Objects):
        if getattr(o, "ObjectToGround", None) == lt:
            a.removeObject(o.Name)
    a.removeObject(lt.Name)
    a.recompute()
    pump()
    status, _ = SyncBinder.sync(native)
    ok &= check("Instanz geloescht", "Instanz" in status and dist(before, native.Shape) < 1e-12, status)

    for d in list(App.listDocuments()):
        App.closeDocument(d)
    SyncBinder.unregister()
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
