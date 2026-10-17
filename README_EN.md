# Naraka NR Character Linker

[中文说明](README.md)

Blender add-on for importing Ninja Ripper `.nr` captures from Naraka: Bladepoint, selecting a likely character group, connecting captured textures, and aligning the static character in Blender.

## Features

- Reads Pre-VS triangle meshes from a `frame_*` capture folder.
- Automatically filters duplicate draw channels and ranks likely character groups.
- Creates UV maps and Principled BSDF materials with color and normal textures.
- Converts captured texture files through FFmpeg when needed.
- Places the character upright with feet at `Z = 0` and the face toward Blender `-Y`.
- Creates front/back cameras and simple lights for inspection.
- Repairs detached face, eye, hair-cap, and hair-card draw channels found in some captures.
- Removes invalid triangles and recalculates normals; solid body and clothing meshes can use level 0–2 subdivision for display refinement.

## Install

1. Download `naraka_nr_character_linker_addon.zip` from the GitHub Releases page.
2. In Blender 4.2 or newer, open **Edit > Preferences > Get Extensions**, open the top-right menu, and choose **Install from Disk**.
3. In Blender 3.6–4.1, use **Edit > Preferences > Add-ons > Install**.
4. Select the downloaded ZIP and enable **Naraka NR Character Linker**.
5. In the 3D View, press `N`, then open the **Naraka NR** tab.

The ZIP must contain a top-level `r_character_linker` folder with `__init__.py` inside it. The Release package follows this layout.

## Use

1. Set **Capture folder** to a `frame_0` or `frame_1` folder that contains `.nr` files.
2. Leave **Group ID** empty for automatic detection. If the result is not the intended character, enter the numeric group from the file names, such as `37` or `1007`.
3. Set **FFmpeg path** when DDS or another format needs conversion. Leave it empty when `ffmpeg` is available on the system `PATH`.
4. Optionally set **Output folder**. If it is empty, converted textures are written beside the saved `.blend`, or to `Naraka_NR_Output` when the file has not been saved yet.
5. Click **Import and link character**.

Before importing, you can adjust **Repair detached face and hair** and **Geometry refinement**. The repair option is enabled by default and aligns head-related draw channels to the captured face. Refinement defaults to level 1; hair cards and repaired head cards are excluded so their transparent silhouettes are preserved.

The imported meshes are placed in the `NR_Character` collection. Converted textures are written under the selected output folder's `textures` directory.

## If Automatic Group Detection Chooses the Wrong Mesh

Automatic detection works with common Naraka capture layouts, but a scene can contain several similar groups. If the wrong character is imported:

1. Check the captured file names, for example `mesh_37_....nr`.
2. Enter `37` in **Group ID**.
3. Click **Import and link character** again.

## Limitations

Ninja Ripper captures generally do not contain the game's original skeleton, skin weights, animation controllers, or proprietary shaders. This add-on restores a static mesh, UVs, and the main captured textures; it cannot recreate the complete in-game material or animation system.

Texture conversion changes the file format but does not add detail that was not present in the capture. If the captured texture is low resolution, the Blender texture will have the same limitation.

The add-on does not modify the original capture folder.

## Project Layout

```text
r_character_linker/
  __init__.py          # Blender UI, importer, materials, alignment
  nrfile.py            # Ninja Ripper .nr parser
  README_中文.md        # Chinese usage notes
LICENSE                # MIT license
README.md              # Chinese project documentation
README_EN.md           # English project documentation
CONTRIBUTING.md        # Contribution guide
```

## License

This project is released under the [MIT License](LICENSE). You may use, modify, and redistribute the code, provided that the copyright and license notice are retained.

The add-on code is separate from game models, textures, and capture files. Do not upload game assets or `.nr` captures to a public repository unless you have the right to distribute them.

## Contributing

Issues and pull requests are welcome. When reporting an importer problem, include the Blender version, operating system, capture format, group ID, and error message when available. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
