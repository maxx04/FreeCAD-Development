# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check of DocObserver.rename_document_with_references() in a throwaway project folder:
a part is renamed while assembly A (open) and assembly B (closed, plus an absolute path in a
spreadsheet cell) link to it. Expected: all references point to the new file, the old file is
a .FCBak, nothing else in B changed, and B reopens with a working link.

Run inside FreeCAD with GUI (e.g. under Xvfb):
    <sandbox>/standalone-check/kinematic-tests/common/run-test.sh <freecad> tests/fc_docobserver_rename_check.py
Prints "RESULT: PASS" or "RESULT: FAIL".
"""
import glob
import os
import sys
import tempfile
import zipfile

import FreeCAD as App

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import DocObserver  # noqa: E402


def check(label, ok, detail=""):
    print(f"{label}: {detail} -> {'OK' if ok else 'FEHLER'}")
    return ok


def xml_of(path):
    with zipfile.ZipFile(path) as z:
        return z.read("Document.xml").decode("utf-8")


def main():
    ok = True
    proj = os.path.join(tempfile.mkdtemp(prefix="fcproj"), "PROJ_TEST")
    os.makedirs(proj)
    open(os.path.join(proj, "PROJ_TEST.json"), "w").write("{}")
    old = os.path.join(proj, "T_001_Alt.FCStd")
    new = os.path.join(proj, "T_001_Neu.FCStd")

    part = App.newDocument("T_001_Alt")
    body = part.addObject("Part::Box", "Teil")
    body.addProperty("App::PropertyString", "ArticleID", "FCProject_PDM").ArticleID = "T_001"
    body.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM").Bezeichnung = "Neu"
    part.recompute()
    part.saveAs(old)

    docs = {}
    for name in ("A", "B"):
        d = App.newDocument(name)
        d.saveAs(os.path.join(proj, f"{name}.FCStd"))  # Link in fremdes Dokument braucht gespeichertes
        link = d.addObject("App::Link", "Link")
        link.LinkedObject = body
        if name == "B":
            sheet = d.addObject("Spreadsheet::Sheet", "Stueckliste")
            sheet.set("A1", "'" + old)
        d.recompute()
        d.save()
        docs[name] = d
    b_path = docs["B"].FileName
    App.closeDocument(docs["B"].Name)
    before = {}
    with zipfile.ZipFile(b_path) as z:
        for info in z.infolist():
            before[info.filename] = z.read(info)

    found = DocObserver.find_referencing_files(proj, old)
    ok &= check("Verweisende Dateien gefunden", sorted(map(os.path.basename, found)) == ["A.FCStd", "B.FCStd"],
                ", ".join(map(os.path.basename, found)))

    result = DocObserver.rename_document_with_references(part, new)
    backups = glob.glob(os.path.join(proj, "T_001_Alt.*.FCBak"))
    ok &= check("Neue Datei, alte als Sicherung", os.path.exists(new) and not os.path.exists(old) and len(backups) == 1,
                f"neu {os.path.exists(new)}, alt {os.path.exists(old)}, Sicherungen {len(backups)}")

    xb = xml_of(b_path)
    ok &= check("B (geschlossen): XLink umgestellt", 'file="T_001_Neu.FCStd"' in xb and 'file="T_001_Alt.FCStd"' not in xb)
    ok &= check("B: Pfad in Tabellenzelle umgestellt", new in xb and old not in xb)
    with zipfile.ZipFile(b_path) as z:
        same = all(z.read(n) == data for n, data in before.items() if n != "Document.xml")
        names = sorted(z.namelist()) == sorted(before)
    ok &= check("B: übrige Einträge unverändert", same and names)

    a = docs["A"]
    a.save()
    xa = xml_of(a.FileName)
    ok &= check("A (geöffnet): nach Speichern neuer Verweis", 'file="T_001_Neu.FCStd"' in xa and "T_001_Alt" not in xa,
                f"offen und ungespeichert gemeldet: {result['open_unsaved']}")

    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)
    b = App.openDocument(b_path)
    linked = b.getObject("Link").LinkedObject
    ok &= check("B neu geöffnet: Link löst auf die neue Datei auf",
                linked is not None and os.path.abspath(linked.Document.FileName) == new,
                linked.Document.FileName if linked else "kein Ziel")
    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)

    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    main()
