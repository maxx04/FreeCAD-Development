# FCProject: Nachrüst-Macro - ergänzt bei bereits BESTEHENDEN PDM-Objekten (aus der Zeit vor dem
# LCS-Fix vom 2026-08-17, siehe resources/docs/CONSTRAINTS.md) das dort geforderte ECHTE
# App::LocalCoordinateSystem, falls es noch fehlt. Neu erstellte Objekte bekommen es bereits
# automatisch (Utils.add_local_coordinate_system(), von allen fünf Creatorn P/A/R/G/B aufgerufen) -
# dieses Macro schließt die Lücke rückwirkend für vorhandene .FCStd-Dateien.
#
# Nutzung (FreeCAD: Makro > Makros... > Ausführen, oder per freecadcmd):
#   Fragt interaktiv nach einem Projektordner (z.B. .../Arbeitsordner/PROJ_U20) und durchsucht ihn
#   REKURSIV nach allen .FCStd-Dateien. Startet IMMER zuerst einen Probelauf (nichts wird
#   geschrieben) und fragt danach nach, ob die gefundenen Lücken tatsächlich geschlossen werden
#   sollen. Bei "Ja" wird vor dem ersten Überschreiben je Datei automatisch eine .bak-Sicherungs-
#   kopie angelegt (falls noch keine existiert), dann gespeichert.
#
# Auch direkt aus der Python-Konsole nutzbar für gezieltere Läufe:
#   import RetrofitLCS
#   RetrofitLCS.retrofit_folder(r"C:/.../PROJ_U20", dry_run=True)   # nur Bericht
#   RetrofitLCS.retrofit_folder(r"C:/.../PROJ_U20", dry_run=False)  # tatsächlich anwenden

import os
import sys
import glob
import shutil

import FreeCAD as App

# --- sys.path-Bootstrap für Utils.py (identisch zu InitGui.py) - macht das Macro auch nutzbar,
# ohne dass die FCProject-Werkbench in dieser Sitzung schon aktiviert wurde. ---
_user_mod_dir = os.path.join(App.getUserAppDataDir(), "Mod", "FCProject")
if not os.path.exists(_user_mod_dir):
    _user_mod_dir = os.path.join(App.getHomePath(), "Mod", "FCProject")
if _user_mod_dir not in sys.path:
    sys.path.append(_user_mod_dir)

import Utils  # noqa: E402  (erst nach dem sys.path-Bootstrap importierbar)


def _find_pdm_root(doc):
    """Findet das EINE PDM-Root-Objekt der Datei (siehe CONSTRAINTS.md: 'In einem Datei nur ein
    Objekt') - erkannt an der ArticleID-Property, die alle fünf Creator (P/A/R/G/B) setzen."""
    for obj in doc.Objects:
        if hasattr(obj, "ArticleID") and getattr(obj, "ArticleID", None):
            return obj
    return None


def _has_real_lcs(root):
    """Dieselbe Logik wie AssemblyPatternCreator._is_real_lcs(): App::Origin erbt in FreeCAD selbst
    von App::LocalCoordinateSystem, zählt hier aber bewusst NICHT als 'echtes' LCS."""
    candidates = list(getattr(root, "OutList", []) or []) + list(getattr(root, "Group", []) or [])
    for child in candidates:
        if child is None:
            continue
        try:
            if child.isDerivedFrom("App::LocalCoordinateSystem") and not child.isDerivedFrom("App::Origin"):
                return True
        except Exception:
            continue
    return False


def _backup(file_path):
    backup_path = file_path + ".bak"
    if not os.path.exists(backup_path):
        shutil.copy2(file_path, backup_path)
    return backup_path


def retrofit_folder(project_dir, dry_run=True):
    """Durchsucht project_dir rekursiv nach .FCStd-Dateien, ergänzt am PDM-Root-Objekt (ArticleID)
    ein fehlendes echtes LCS und speichert. Mit dry_run=True (Standard) wird NICHTS geschrieben,
    nur ein Bericht ausgegeben - erst mit dry_run=False wird tatsächlich gespeichert (inkl.
    .bak-Sicherungskopie der Originaldatei, falls noch keine existiert). Gibt ein Dict mit den
    vier Ergebnislisten zurück."""
    if not os.path.isdir(project_dir):
        App.Console.PrintError(f"FCProject Retrofit: Ordner nicht gefunden: {project_dir}\n")
        return None

    fcstd_files = sorted(glob.glob(os.path.join(project_dir, "**", "*.FCStd"), recursive=True))
    App.Console.PrintMessage(
        f"FCProject Retrofit: {len(fcstd_files)} .FCStd-Datei(en) unter '{project_dir}' gefunden "
        f"({'Probelauf - es wird NICHTS gespeichert' if dry_run else 'Änderungen werden gespeichert!'}).\n"
    )

    already_ok, fixed, skipped, failed = [], [], [], []

    for file_path in fcstd_files:
        already_open_name = next(
            (name for name, d in App.listDocuments().items() if getattr(d, "FileName", "") == file_path),
            None,
        )
        opened_by_us = False

        try:
            if already_open_name:
                doc = App.getDocument(already_open_name)
            else:
                doc = App.openDocument(file_path)
                opened_by_us = True

            root = _find_pdm_root(doc)

            if root is None:
                skipped.append(file_path)
                App.Console.PrintWarning(
                    f"FCProject Retrofit: Kein PDM-Objekt (ArticleID) in '{file_path}' gefunden - übersprungen.\n"
                )
            elif _has_real_lcs(root):
                already_ok.append(file_path)
            elif dry_run:
                fixed.append(file_path)
                App.Console.PrintMessage(f"FCProject Retrofit: [Probelauf] würde LCS ergänzen: '{file_path}'\n")
            else:
                Utils.add_local_coordinate_system(root)
                doc.recompute()
                _backup(file_path)
                doc.save()
                fixed.append(file_path)
                App.Console.PrintMessage(f"FCProject Retrofit: LCS ergänzt + gespeichert: '{file_path}'\n")

        except Exception as e:
            failed.append((file_path, str(e)))
            App.Console.PrintError(f"FCProject Retrofit: Fehler bei '{file_path}': {str(e)}\n")
        finally:
            # Nur schließen, was wir selbst geöffnet haben - ein Dokument, das der Nutzer schon
            # vorher offen hatte, bleibt unangetastet offen.
            if opened_by_us:
                try:
                    App.closeDocument(doc.Name)
                except Exception as close_err:
                    App.Console.PrintWarning(
                        f"FCProject Retrofit: Konnte '{file_path}' nicht wieder schließen: {str(close_err)}\n"
                    )

    fixed_label = "Würden ergänzt (Probelauf)" if dry_run else "Ergänzt und gespeichert"
    App.Console.PrintMessage(
        "\nFCProject Retrofit: fertig.\n"
        f"  Bereits ok:                     {len(already_ok)}\n"
        f"  {fixed_label}:{' ' * max(1, 20 - len(fixed_label))}{len(fixed)}\n"
        f"  Übersprungen (kein PDM-Objekt):  {len(skipped)}\n"
        f"  Fehlgeschlagen:                  {len(failed)}\n"
    )
    if failed:
        App.Console.PrintWarning(
            "FCProject Retrofit: Fehlgeschlagene Dateien:\n"
            + "\n".join(f"  - {p}: {e}" for p, e in failed)
            + "\n"
        )
    if dry_run and fixed:
        App.Console.PrintMessage(
            "FCProject Retrofit: Das war nur ein Probelauf - retrofit_folder(pfad, dry_run=False) "
            "für das tatsächliche Anwenden aufrufen.\n"
        )

    return {"already_ok": already_ok, "fixed": fixed, "skipped": skipped, "failed": failed}


def _run_interactive():
    """Wird beim direkten Ausführen als FreeCAD-Macro aufgerufen: fragt nach dem Projektordner,
    macht immer zuerst einen Probelauf und fragt danach nach, ob wirklich gespeichert werden soll."""
    if not App.GuiUp:
        App.Console.PrintError(
            "FCProject Retrofit: Ohne GUI kein Ordner-Dialog möglich - stattdessen "
            "RetrofitLCS.retrofit_folder(pfad, dry_run=...) direkt aufrufen.\n"
        )
        return

    import FreeCADGui as Gui
    from PySide6 import QtWidgets

    project_dir = QtWidgets.QFileDialog.getExistingDirectory(
        Gui.getMainWindow(), "FCProject Retrofit: Projektordner wählen (wird rekursiv durchsucht)"
    )
    if not project_dir:
        App.Console.PrintMessage("FCProject Retrofit: kein Ordner gewählt, breche ab.\n")
        return

    result = retrofit_folder(project_dir, dry_run=True)
    if not result or not result["fixed"]:
        QtWidgets.QMessageBox.information(
            Gui.getMainWindow(), "FCProject Retrofit",
            "Keine Datei braucht ein nachträgliches LCS - nichts zu tun."
        )
        return

    answer = QtWidgets.QMessageBox.question(
        Gui.getMainWindow(), "FCProject Retrofit",
        f"{len(result['fixed'])} Datei(en) fehlt ein echtes LCS.\n\n"
        "Jetzt wirklich ergänzen und speichern? Von jeder betroffenen Datei wird vorher automatisch "
        "eine .bak-Sicherungskopie angelegt.",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
    )
    if answer == QtWidgets.QMessageBox.Yes:
        retrofit_folder(project_dir, dry_run=False)


if __name__ == "__main__":
    _run_interactive()
