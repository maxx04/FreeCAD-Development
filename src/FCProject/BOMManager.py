# Macro Version: 4.2.5 - FCProject: BOMManager mit direktem C++ .ArticleID.Value Auszug
import os
import csv
import FreeCAD as App

class BOMManager:
    """Struktur-BOM Engine, die PDM-Werte direkt aus .ArticleID.Value im C++ Kern liest."""

    def __init__(self, active_doc=None):
        self.doc = active_doc if active_doc else App.ActiveDocument

    def _resolve_pdm_value(self, obj, prop_name):
        """Sucht eine PDM-Eigenschaft auf allen Ebenen und liest den echten C++ .Value aus."""
        if not obj:
            return None
            
        # 1. Direkt am übergebenen Element prüfen
        if hasattr(obj, prop_name) and getattr(obj, prop_name):
            prop_obj = getattr(obj, prop_name)
            # WICHTIG: Wenn es eine FreeCAD-Property ist, ziehen wir den reinen Text über .Value!
            if hasattr(prop_obj, "Value"):
                val = str(prop_obj.Value).strip()
            else:
                val = str(prop_obj).strip()
                
            if val and val != "-":
                return val
            
        # 2. Wenn es ein Link ist, im verlinkten echten Quell-Dokumentenobjekt suchen
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            res = self._resolve_pdm_value(obj.LinkedObject, prop_name)
            if res: return res

        # 3. Wenn es ein Gruppen-Container ist, in den inneren Unterelementen suchen
        if hasattr(obj, "Group"):
            for child in obj.Group:
                if child.Label.startswith("BOM-Ref:"):
                    continue
                if hasattr(child, prop_name) and getattr(child, prop_name):
                    prop_obj = getattr(child, prop_name)
                    if hasattr(prop_obj, "Value"):
                        val = str(prop_obj.Value).strip()
                    else:
                        val = str(prop_obj).strip()
                        
                    if val and val != "-":
                        return val
        return None

    def _extract_pdm_data(self, obj):
        """Sammelt Metadaten direkt und unverfälscht aus den echten PDM-Properties."""
        # KORREKTUR: Zieht den sauberen, reinen Wert direkt über die neue .Value-Kaskade!
        article_id = self._resolve_pdm_value(obj, "ArticleID")
        if not article_id:
            pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
            article_id = pdm_obj.Name

        # Bezeichnung auflösen
        bezeichnung = self._resolve_pdm_value(obj, "Bezeichnung")
        if not bezeichnung:
            profil_typ = self._resolve_pdm_value(obj, "ProfilTyp")
            if profil_typ:
                bezeichnung = profil_typ
            else:
                pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
                bezeichnung = pdm_obj.Label.split('_')[-1].rstrip('_') if '_' in pdm_obj.Label else pdm_obj.Label

        # Werkstoff auflösen
        material = self._resolve_pdm_value(obj, "MaterialName")
        if not material:
            pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
            if hasattr(pdm_obj, "ShapeMaterial") and pdm_obj.ShapeMaterial:
                material = getattr(pdm_obj.ShapeMaterial, "Name", "-")
            else:
                material = self._resolve_pdm_value(obj, "ShapeMaterial")
                if not material: material = "-"

        # Rohling-Verknüpfung auflösen
        rohteil = self._resolve_pdm_value(obj, "BasiertAufHalbzeug")
        if not rohteil: rohteil = "-"

        return {
            "ArticleID": article_id,
            "Bezeichnung": bezeichnung,
            "Material": material,
            "Rohling": rohteil
        }

    def _scan_recursive(self, current_obj, current_index, bom_list, visited_objects):
        if current_obj in visited_objects:
            return
        visited_objects.add(current_obj)

        scan_target = current_obj.LinkedObject if hasattr(current_obj, "LinkedObject") and current_obj.LinkedObject else current_obj
        children = getattr(scan_target, "Group", [])

        valid_children = []
        for child in children:
            if child.Label.startswith("BOM-Ref:") or "Bill_of_Materials" in child.Label or "Bills_of_Materials" in child.Name:
                continue
            if child.isDerivedFrom("App::Origin") or "Origin" in child.Name or "Joints" in child.Name:
                continue
                
            has_id = self._resolve_pdm_value(child, "ArticleID")
            if has_id:
                valid_children.append(child)

        for sub_idx, child in enumerate(valid_children, start=1):
            new_index = f"{sub_idx}" if current_index == "" else f"{current_index}.{sub_idx}"

            pdm_info = self._extract_pdm_data(child)
            
            bom_list.append([
                new_index,
                pdm_info["ArticleID"],
                pdm_info["Bezeichnung"],
                pdm_info["Material"],
                pdm_info["Rohling"],
                "1"
            ])

            target_child = child.LinkedObject if hasattr(child, "LinkedObject") and child.LinkedObject else child
            if hasattr(target_child, "Group") and target_child.Group:
                self._scan_recursive(child, new_index, bom_list, visited_objects)

    def generate_structural_bom(self):
        bom_list = []
        if not self.doc:
            return bom_list

        root_assembly = None
        for obj in self.doc.Objects:
            if obj.isDerivedFrom("Assembly::AssemblyObject"):
                is_child = False
                for other in self.doc.Objects:
                    if hasattr(other, "Group") and obj in other.Group:
                        is_child = True
                        break
                if not is_child:
                    root_assembly = obj
                    break

        if not root_assembly:
            for obj in self.doc.Objects:
                if obj.isDerivedFrom("App::Part") and not obj.Label.startswith("BOM-Ref:"):
                    root_assembly = obj
                    break

        if not root_assembly:
            return bom_list

        root_index = "1"
        pdm_info = self._extract_pdm_data(root_assembly)
        bom_list.append([
            root_index,
            pdm_info["ArticleID"],
            pdm_info["Bezeichnung"],
            pdm_info["Material"],
            pdm_info["Rohling"],
            "1"
        ])

        visited = set()
        self._scan_recursive(root_assembly, root_index, bom_list, visited)

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
                writer.writerow(["Position (Struktur-Index)", "Artikel-ID", "Benennung", "Werkstoff", "Rohling/Halbzeug", "Menge"])
                for row in structural_rows:
                    writer.writerow(row)
            return csv_path
        except Exception as e:
            App.Console.PrintError(f"FCProject BOM-Fehler: {str(e)}\n")
            return None
