# Blendkit native asset import

ATLAS imports reviewed Free-plan CC0 assets acquired through the official Blendkit Blender add-on. Install the pinned stable release **v3.21.7.261119** in an isolated Blender profile. The release ZIP SHA-256 is `762c731f1d530a9adf1304ffe60b3de8465e9f370815f5eec541a3cec00477c5`. Installation, add-on loading, anonymous Free-plan acquisition and native import were exercised on Blender 5.2.3 LTS. [Official release](https://github.com/BlenderKit/Blendkit/releases/tag/v3.21.7.261119) · [Installation instructions](https://www.blendkit.com/get-blendkit/)

## Acquire and prepare a native file

1. In a dedicated Windows PowerShell session, set `BLENDER_USER_RESOURCES` to an empty directory reserved for Blendkit. Launch Blender with `--disable-autoexec`, then install the pinned ZIP using **Preferences → Add-ons → Install from Disk**. Keep the Blendkit download directory inside the dedicated workspace.
2. Use the official gallery or add-on to find the asset. Review the item’s Free access, Creative Commons Zero license, author, and canonical gallery URL. The official add-on supports anonymous downloads for eligible Free assets. Enter any required account information in Blendkit’s own interface. [Official add-on workflow](https://github.com/BlenderKit/Blendkit) · [Licenses](https://www.blendkit.com/docs/licenses/)
3. Choose **Append** in Blendkit’s import settings and add the asset to an otherwise empty Blender scene. Keep the provider download in the local add-on cache. Pack permitted image dependencies into the staging file and save a separate uncompressed `.blend`. Record the exact object or collection names in the Outliner. [Official append workflow](https://www.blendkit.com/faq-frequently-asked-questions/)
4. Create a provenance JSON document with `name`, `creator`, canonical `source_url`, `license_id: "CC0-1.0"`, the full `license_text`, `approval: "approved"`, `render_allowed: true`, and `redistribution_allowed: false`. Include attribution, a description and useful tags. The provider UUID is the ID in the canonical `/asset-gallery-detail/…/` URL. [CC0 legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt)

The private workflow permits local editable production and rendered output. Keep the native source, GLB, and editable scene in local private storage. Free access is independent of the asset license. The native workflow rejects royalty-free and Full-plan submissions. The private policy reflects Blendkit’s terms for redistributing electronic projects and assets. [User terms, §5](https://www.blendkit.com/terms-and-conditions-2026/) · [Licensing FAQ](https://www.blendkit.com/docs/licenses/licensing-faq/)

## Register and inspect

```powershell
atlas assets import-blendkit 'outputs/blendkit-addon-smoke/Atlas Blendkit Review.blend' `
  --id blendkit-small-wooden-table `
  --provider-asset-id e1901884-2e47-4a82-8a2e-bfd573200c6f --plan free `
  --provenance outputs/blendkit-addon-smoke/table.provenance.json `
  --collection 'Small Wooden Table 01' --library outputs/v052-library --cache outputs/v052-acquisition
```

Repeat `--object` to select individual objects or repeat `--collection` for named collections. Include the parents of selected objects. The conversion preserves object hierarchy, surface geometry, UV sets, and compatible Principled PBR channels. It incorporates packed PNG, JPEG, and bounded scanline OpenEXR textures into the validated GLB. Blender can combine the metallic and roughness maps into one image. `<library>/blendkit-private/` retains the immutable staged input and its JSON receipt. The asset version’s registry record identifies the production GLB and inspection.

The native profile accepts uncompressed little-endian 64-bit Blender files up to 256 MiB. It limits selection to 512 meshes and empties, 2 million vertices and triangles, and 32 packed textures up to 4096 pixels per edge. Conversion uses a separate factory-startup Blender process, a temporary profile, disabled auto-execution, offline mode, and a timeout. Files with linked libraries or text blocks fail preflight. Drivers, animations, rigs, shape keys, external image paths, procedural node groups, and modifiers other than a single triangulation modifier are outside this profile. Cameras, world lighting, and standalone materials have their own representation in ATLAS projects. The isolated process uses the local Blender executable and operating-system account.

## Verified example

On 25 November 2026 the pinned add-on downloaded and appended **Small Wooden Table 01** at 2K anonymously. The official gallery and appended Blendkit metadata both identified Free access and CC0. Ulan Cabanilla created the original for Poly Haven, which supplied the Blendkit listing. [Blendkit gallery](https://www.blendkit.com/asset-gallery-detail/e1901884-2e47-4a82-8a2e-bfd573200c6f/) · [Original Poly Haven credit](https://polyhaven.com/a/small_wooden_table_01)

| Stage | SHA-256 | Bytes |
|---|---|---:|
| Official add-on cache file | `07767225bdefb5abf7a69155df97b7714ca11717cf16c9cde08350bea5fd90c0` | 11,093,631 |
| Uncompressed staged collection | `f113255edd22cfcc7a5556a2308634e60d52e9a7127882d4c615f9dfb426f319` | 11,950,739 |
| Inspected GLB | `270f44a98df931cde535ca4404d1ce1da03524491e16e5a97b794c5902b04c0f` | 16,660,332 |

The approved `blendkit-small-wooden-table@1` contains 3,410 triangles, one material, and three packed 2048×2048 textures. Inspection measured 0.916 × 0.440 × 0.533 m and verified the Base Color, Metallic, Roughness, and Normal connections. The source contained four packed maps, including two scanline OpenEXR files. This was a provider download. The opt-in integration suite uses local Blender-generated fixtures to check native object and collection loading, material and texture retention, unsafe file rejection, and re-opening a rendered production scene.

Render the demonstration with the inspected table and `polyhaven-chinese_screen_panels@1` in the same library.

```powershell
atlas render examples/22_blendkit_table.json --asset-library outputs/v052-library --output outputs/v052-renders
```
