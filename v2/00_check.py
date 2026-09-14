"""Etape 0 — verification de l'environnement. N'importe rien, ne rend rien.

    blender -b -P v2/00_check.py

Sort en erreur si quelque chose manque, pour que la suite ne demarre pas sur un
environnement incomplet.
"""
import sys

REQUIS_BLENDER = (3, 6)


def ligne(cle, valeur, ok=None):
    marque = "   " if ok is None else ("ok " if ok else "!! ")
    print(f"{marque}{cle:<28} {valeur}")


def main() -> int:
    try:
        import bpy
    except ImportError:
        print("!! bpy introuvable : lancer ce script via `blender -b -P`, pas via python.")
        return 1

    manques = []

    version = bpy.app.version
    assez = version[:2] >= REQUIS_BLENDER
    ligne("Blender", bpy.app.version_string, assez)
    if not assez:
        manques.append(f"Blender {REQUIS_BLENDER[0]}.{REQUIS_BLENDER[1]} minimum")

    binaire = bpy.app.binary_path or "(module bpy, pas d'executable)"
    ligne("executable", binaire, bool(bpy.app.binary_path))
    if not bpy.app.binary_path:
        manques.append("aucun executable Blender : bpy est ici un module pip, "
                       "pas l'application")

    ligne("Python embarque", sys.version.split()[0])
    ligne("plateforme", sys.platform)

    # --- Blosm ---
    try:
        import addon_utils
    except ImportError:
        ligne("Blosm", "addon_utils indisponible", False)
        manques.append("addon_utils : ce n'est pas un vrai Blender")
        addon_utils = None

    if addon_utils is not None:
        noms = {m.__name__ for m in addon_utils.modules()}
        nom = next((n for n in noms if "blosm" in n.lower()
                    or "blender-osm" in n.lower()), None)
        if nom is None:
            ligne("Blosm", "absent", False)
            manques.append("addon Blosm non installe")
        else:
            active = addon_utils.check(nom)[1]
            ligne("Blosm", f"{nom} ({'active' if active else 'INACTIF'})", active)
            if not active:
                manques.append(f"addon {nom} installe mais desactive")
            prefs = bpy.context.preferences.addons.get(nom)
            chemin = getattr(prefs.preferences, "dataDir", None) if prefs else None
            ligne("Blosm dataDir", chemin or "(non defini)", bool(chemin))
            if not chemin:
                manques.append("dataDir de Blosm non defini dans les preferences")

    # --- moteurs de rendu disponibles ---
    moteurs = [e.identifier for e in
               bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    ligne("moteurs", ", ".join(moteurs))
    if "BLENDER_WORKBENCH" not in moteurs:
        manques.append("Workbench indisponible")

    print()
    if manques:
        print("ARRET. Il manque :")
        for m in manques:
            print(f"  - {m}")
        return 1
    print("Environnement complet. On peut passer a l'etape 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
