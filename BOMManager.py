#FCProject: BOMManager mit strikter LinkedObject-Erzwingung für die ID
import os
import csv
import FreeCAD as App
import Utils as Utils

class BOMManager:
    """Struktur-BOM Engine, die Metadaten aus dem verlinkten Kernobjekt liest."""

    def __init__(self, active_doc=None):
        self.doc = active_doc if active_doc else App.ActiveDocument


    def generate_structural_bom(self):
        # Das aktuell ausgewählte Objekt im Baum als Startpunkt nehmen (z.B. die Hauptbaugruppe)
        auswahl = App.Gui.Selection.getSelection()

        if not auswahl:
            App.Console.PrintError("Fehler: Bitte klicke zuerst die Hauptbaugruppe im Baum an!")
            return
        else:
            # Nimm das erste Element, das der Nutzer angeklickt hat
            root_assembly = auswahl[0]

        list = Utils.get_assembly_tree(root_assembly)

        bom_list = []
        level_counters = {}

        for row in list:
            obj, depth, artikel_id = row[0], row[1], row[2]

            if artikel_id not in ('None', None, "", "-"):
                if depth not in level_counters:
                    level_counters[depth] = 0
                level_counters[depth] += 1

                # Tiefere Ebenen zurücksetzen, damit Tiefenwechsel sauber bleiben
                keys_to_delete = [k for k in level_counters.keys() if k > depth]
                for k in keys_to_delete:
                    del level_counters[k]

                structure_index = "-".join(str(level_counters[d]) for d in range(depth + 1) if d in level_counters)
                indent = "  " * depth

                print(f"{indent}- {obj.Label} (Artikel-ID: {artikel_id}) - {Utils._resolve_pdm_value(obj, 'MaterialName')}")  

                #TODO: Doppeltes Auslesen der Artikel-ID vermeiden, da sie bereits in der Liste enthalten ist. Stattdessen direkt die Metadaten aus dem Objekt extrahieren.
                pdm_info = Utils._extract_pdm_data(obj)

                bom_list.append([
                    structure_index,
                    pdm_info["ArticleID"],
                    pdm_info["Bezeichnung"],
                    pdm_info["Material"],
                    pdm_info["Rohling"],
                    pdm_info.get("Preis", 0.0),
                    "1"
               ])

        return bom_list

    def export_to_csv(self, target_dir):
        if not self.doc: return None
        
        structural_rows = self.generate_structural_bom()
        if not structural_rows:
            return None

        csv_filename = f"BOM_Struktur_{self.doc.Name}.csv"
        csv_path = os.path.join(target_dir, csv_filename)

        try:
            with open(csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(["Position (Struktur-Index)", "Artikel-ID", "Benennung", "Werkstoff", "Rohling/Halbzeug", "Preis", "Menge"])
                for row in structural_rows:
                    writer.writerow(row)
            return csv_path
        except Exception as e:
            App.Console.PrintError(f"FCProject BOM-Fehler: {str(e)}\n")
            return None

    def export_to_spreadsheet(self, target_dir):
        """Erstellt ein neues FreeCAD Spreadsheet und importiert die generierte CSV."""
        if not self.doc:
            return None

        csv_path = self.export_to_csv(target_dir)
        if not csv_path:
            return None

        try:
            sheet_name = f"BOM_Spreadsheet_{self.doc.Name}"
            sheet = self.doc.addObject("Spreadsheet::Sheet", sheet_name)

            def column_name(index):
                name = ""
                while index >= 0:
                    name = chr(ord('A') + (index % 26)) + name
                    index = index // 26 - 1
                return name

            price_col = None
            with open(csv_path, mode='r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f, delimiter=',', quotechar='"')
                for row_index, row in enumerate(reader, start=1):
                    if row_index == 1:
                        for col_index, header in enumerate(row):
                            if header.strip().lower() == "preis":
                                price_col = col_index
                    for col_index, cell_value in enumerate(row):
                        cell_name = f"{column_name(col_index)}{row_index}"
                        if row_index > 1 and price_col is not None and col_index == price_col:
                            try:
                                price = float(str(cell_value).replace(',', '.'))
                                sheet.set(cell_name, price)
                            except Exception:
                                sheet.set(cell_name, cell_value)
                        else:
                            sheet.set(cell_name, cell_value)

            self.doc.recompute()
            return sheet
        except Exception as e:
            App.Console.PrintError(f"FCProject Spreadsheet-Fehler: {str(e)}\n")
            return None
