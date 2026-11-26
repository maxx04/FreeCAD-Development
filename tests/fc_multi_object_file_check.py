# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check: several objects in ONE file (against the rule "in einer Datei nur ein Objekt", e.g. a
foreign or imported file), 2026-11-24. A parts file holds Platte and Quader (App::Part containers with an
own ArticleID) and an App::Part "Gruppe" with a box "Innen"; an assembly links all three, Quader
first (the old document-based lookup then returned the Quader link for the Platte).

Checked:
  - SectionSketchFeature._find_top_level_link_for(): link of the object itself, of its container
    (App::Part), unique document fallback kept, ambiguous case -> None
  - DocObserver: no rename prompt for a file with several PDM objects
  - RetrofitLCS: every PDM object of the file gets an LCS
  - ImportComponentCommand: several candidates -> error without chooser, chosen one with chooser

Run inside FreeCAD with GUI (e.g. under Xvfb):
    <sandbox>/sandbox-tests/common/run-test.sh <freecad> tests/fc_multi_object_file_check.py
Prints "RESULT: PASS" or "RESULT: FAIL".
"""
import os
import sys
import tempfile

import FreeCAD as App

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
sys.path.insert(0, os.path.join(HERE, "..", "python", "resources", "macros"))
import DocObserver  # noqa: E402
import ImportComponentCommand  # noqa: E402
import RetrofitLCS  # noqa: E402
import SectionSketchFeature  # noqa: E402


def check(label, ok, detail=""):
    print(f"{label}: {detail} -> {'OK' if ok else 'FEHLER'}")
    return ok


def pdm_part(doc, name, article):
    """PDM-Objekt wie von den Creatorn: Container (hier App::Part) mit ArticleID und Inhalt."""
    part = doc.addObject("App::Part", name)
    part.addProperty("App::PropertyString", "ArticleID", "FCProject_PDM").ArticleID = article
    part.addObject(doc.addObject("Part::Box", name + "Koerper"))
    return part


def label(obj):
    return obj.Label if obj is not None else "None"


def main():
    ok = True
    proj = os.path.join(tempfile.mkdtemp(prefix="fcproj"), "PROJ_TEST")
    os.makedirs(proj)
    open(os.path.join(proj, "PROJ_TEST.json"), "w").write("{}")

    parts = App.newDocument("teile")
    platte = pdm_part(parts, "Platte", "T_001")
    quader = pdm_part(parts, "Quader", "T_002")
    gruppe = parts.addObject("App::Part", "Gruppe")
    innen = parts.addObject("Part::Box", "Innen")
    gruppe.addObject(innen)
    hilf = parts.addObject("Part::Box", "Hilf")  # nicht eingebaut
    parts.recompute()
    parts.saveAs(os.path.join(proj, "teile.FCStd"))

    single = App.newDocument("einzel")
    einzel = single.addObject("Part::Box", "Einzel")
    einzel_hilf = single.addObject("Part::Box", "EinzelHilf")
    single.recompute()
    single.saveAs(os.path.join(proj, "einzel.FCStd"))

    asm_doc = App.newDocument("baugruppe")
    asm_doc.saveAs(os.path.join(proj, "baugruppe.FCStd"))
    links = {}
    for src in (quader, platte, gruppe, einzel):  # Quader zuerst (alter Fehler)
        link = asm_doc.addObject("App::Link", "L_" + src.Name)
        link.LinkedObject = src
        links[src.Name] = link
    asm_doc.recompute()

    find = SectionSketchFeature._find_top_level_link_for
    for name, target, want in (
        ("Platte (zweiter Link in die Datei)", platte, links["Platte"]),
        ("Koerper der Platte (im Container)", parts.getObject("PlatteKoerper"), links["Platte"]),
        ("Quader", quader, links["Quader"]),
        ("Innen im App::Part", innen, links["Gruppe"]),
        ("eindeutiger Rueckfall (einzige Verlinkung der Datei)", einzel_hilf, links["Einzel"]),
        ("mehrdeutig (Objekt nicht eingebaut)", hilf, None),
    ):
        got = find(asm_doc, target)
        ok &= check(f"Link fuer {name}", got is want, f"{label(got)} (erwartet {label(want)})")

    # DocObserver: kein Umbenennen-Angebot bei mehreren PDM-Objekten
    asked = []
    DocObserver._ask_rename = lambda doc, stem: asked.append(stem)
    DocObserver._check_doc(parts)
    from PySide import QtCore
    QtCore.QCoreApplication.processEvents()
    n_pdm = len(DocObserver._find_pdm_objects(parts))
    ok &= check("DocObserver", n_pdm == 2 and not asked, f"{n_pdm} PDM-Objekte, Nachfragen {asked}")

    # RetrofitLCS: beide PDM-Objekte bekommen ein LCS
    for d in list(App.listDocuments()):
        App.closeDocument(d)
    result = RetrofitLCS.retrofit_folder(proj, dry_run=False)
    parts = App.openDocument(os.path.join(proj, "teile.FCStd"))
    with_lcs = [n for n in ("Platte", "Quader") if RetrofitLCS._has_real_lcs(parts.getObject(n))]
    ok &= check("RetrofitLCS", with_lcs == ["Platte", "Quader"],
                f"LCS bei {with_lcs}, ergaenzt in {len(result['fixed'])} Datei(en)")

    # Import: mehrere Kandidaten
    target_doc = App.newDocument("ziel")
    target_doc.saveAs(os.path.join(proj, "ziel.FCStd"))
    cands = ImportComponentCommand.find_import_candidates(parts)
    ok &= check("Import-Kandidaten", [c.Name for c in cands] == ["Platte", "Quader"],
                str([c.Name for c in cands]))
    try:
        ImportComponentCommand.make_import_component(target_doc, parts.FileName)
        ok &= check("Import ohne Auswahl", False, "kein Fehler")
    except RuntimeError as e:
        ok &= check("Import ohne Auswahl", "mehrere Objekte" in str(e), str(e))
    link = ImportComponentCommand.make_import_component(target_doc, parts.FileName, lambda c: c[1])
    ok &= check("Import mit Auswahl", link is not None and link.LinkedObject.Name == "Quader",
                label(link.LinkedObject) if link else "None")
    cancelled = ImportComponentCommand.make_import_component(target_doc, parts.FileName, lambda c: None)
    ok &= check("Import abgebrochen", cancelled is None, str(cancelled))
    single_cands = ImportComponentCommand.find_import_candidates(App.openDocument(os.path.join(proj, "einzel.FCStd")))
    ok &= check("Datei ohne PDM-Objekt: alle Geometrie-Objekte", [c.Name for c in single_cands] == ["Einzel", "EinzelHilf"],
                str([c.Name for c in single_cands]))

    for d in list(App.listDocuments()):
        App.closeDocument(d)
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
