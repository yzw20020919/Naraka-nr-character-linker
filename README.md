# Naraka NR Character Linker

Blender add-on for importing Ninja Ripper `.nr` captures from Naraka: Bladepoint, selecting a likely character group, connecting captured textures, and aligning the static character in Blender.

## Features

- Reads Pre-VS triangle meshes from a `frame_*` capture folder.
- Automatically filters duplicate draw channels and ranks likely character groups.
- Creates UV maps and Principled BSDF materials with color and normal textures.
- Converts captured texture files through FFmpeg when needed.
- Places the character upright with feet at `Z = 0` and the face toward Blender `-Y`.
- Creates front/back cameras and simple lights for inspection.

## Install

1. Download the repository as a ZIP, or download the ZIP from the Releases page.
2. In Blender 4.2 or newer, open **Edit > Preferences > Get Extensions**, open the top-right menu, and choose **Install from Disk**. In Blender 3.6–4.1, use **Preferences > Add-ons > Install**.
3. Select the downloaded ZIP and enable **Naraka NR Character Linker**.
4. In the 3D View, press `N`, then open the **Naraka NR** tab.

For normal installation, the ZIP must contain the top-level `r_character_linker` folder with `__init__.py` inside it. The Release asset generated for this repository follows that layout.

## Use

1. Set **Capture folder** to a `frame_0` or `frame_1` folder that contains `.nr` files.
2. Leave **Group ID** empty for automatic detection. If the result is not the intended character, enter the numeric group from the file names, such as `37` or `1007`.
3. Set **FFmpeg path** when DDS or another format needs conversion. The field can be left empty when `ffmpeg` is available on the system `PATH`.
4. Optionally set **Output folder**. If it is empty, converted textures are written beside the saved `.blend`, or to `Naraka_NR_Output` when the file has not been saved yet.
5. Click **Import and link character**.

The imported meshes are placed in the `NR_Character` collection. Converted textures are written under the selected output folder's `textures` directory.

## Limitations

Ninja Ripper captures generally do not contain the game's original skeleton, skin weights, animation controllers, or proprietary shaders. This add-on restores a static mesh, UVs, and the main captured textures; it cannot recreate the complete in-game material or animation system. Texture conversion does not add detail that was not present in the capture.

The add-on does not modify the original capture folder.

## Project layout

```text
r_character_linker/
  __init__.py          # Blender UI, importer, materials, alignment
  nrfile.py            # Ninja Ripper .nr parser
  README_中文.md        # Chinese usage notes
LICENSE
README.md
```

## License

MIT. See [LICENSE](LICENSE).
