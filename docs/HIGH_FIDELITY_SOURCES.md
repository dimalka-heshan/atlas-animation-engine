# High-fidelity source assets

ATLAS 0.5.1 indexes Poly Haven models, HDRIs and textures, ambientCG materials, and a reviewed historical object from Smithsonian Open Access. Catalog synchronization stores metadata locally. The download command fetches one selected source and requires an explicit network call. GLB registry versions require Blender inspection before use in a render.

| Source | Derivatives | License evidence |
| --- | --- | --- |
| Poly Haven | Models from glTF with embedded PNG or JPEG dependencies, material JPEG maps, and HDRI HDR files at 1K, 2K or 4K where offered | [CC0 asset license](https://polyhaven.com/license) and [Poly Haven API terms and attribution](https://polyhaven.com/our-api) |
| ambientCG | PBR JPEG or PNG archives at 1K, 2K or 4K where offered | [CC0 asset license](https://docs.ambientcg.com/license/) and [API v3 asset and download metadata](https://docs.ambientcg.com/api/v3/assets/) |
| Smithsonian Open Access | The reviewed Rococo Side Chair in a fixed uncompressed GLB derivative | [CC0 on the museum object record](https://3d.si.edu/object/3d/side-chair%3Aff607e3c-3d88-4422-a246-3976aa4839dc) and [3D file search API](https://3d-api.si.edu/api-docs/) |

The Poly Haven service requires an identifiable API User-Agent and source attribution. CLI catalog entries display “Powered by Poly Haven.” The assets are available under CC0. [Poly Haven API](https://polyhaven.com/our-api)

## Acquire a scene asset

```powershell
$python = '.\.venv\Scripts\python.exe'
$cache = 'outputs/v051-acquisition'
$library = 'outputs/v051-library'
& $python -m apps.cli assets sync polyhaven --cache $cache
& $python -m apps.cli assets catalog 'wooden crate' --category environment --cache $cache
& $python -m apps.cli assets download polyhaven-wooden_crate_01 --resolution 2k --format gltf --cache $cache --library $library
& $python -m apps.cli assets inspect polyhaven-wooden_crate_01 --version 1 --library $library
& $python -m apps.cli assets sync smithsonian --cache $cache
& $python -m apps.cli assets download smithsonian-rococo-side-chair --format glb --cache $cache --library $library
& $python -m apps.cli assets inspect smithsonian-rococo-side-chair --version 1 --library $library
```

Poly Haven's API supplies the exact glTF file and dependency list for each resolution. ATLAS checks the declared byte count and MD5 of every file, records its SHA-256, and embeds the binary geometry and images in a static GLB. The GLB registry then checks the derived file with its standard static profile. Lower texture resolution reduces texture transfer and memory use. Shared mesh binaries can have the same triangle count across resolutions.

The Smithsonian adapter selects an exact published derivative for Cooper Hewitt accession 2006-5-1, dated 1750–60 and probably made in Birmingham, England. It retains the object record, museum credit, source GLB hash and unit conversion in the provenance. The source coordinates match millimeters when compared with the dimensions on the museum record. A single root scale converts the derivative to meters while retaining its mesh and image bytes. The catalog is curated per object and its license comes from the exact museum record. [Cooper Hewitt Side Chair](https://3d.si.edu/object/3d/side-chair%3Aff607e3c-3d88-4422-a246-3976aa4839dc)

## Acquire and use ground materials

```powershell
& $python -m apps.cli assets sync ambientcg --cache $cache
& $python -m apps.cli assets catalog 'paving stone' --category material --cache $cache
& $python -m apps.cli assets download ambientcg-pavingstones036 --resolution 1k --format jpg --cache $cache
```

Use the returned `fingerprint` with the asset ID under `scene.environment.ground_texture`. This pins the texture bytes independently of any subsequent download of a different derivative. Resolution describes the longest side of the archived images. `texture_repeats_per_meter` sets scene tiling.

```json
{
  "ground_texture": {
    "id": "ambientcg-pavingstones036",
    "fingerprint": "998270728cdaa7fb80dbc627a6dc6ba9780fb4ac2f5117577060aa2b1437990a"
  },
  "texture_repeats_per_meter": 1
}
```

The adapter requires color, roughness, and OpenGL normal maps and retains metallic, height, displacement, ambient occlusion, opacity, and emission when supplied. Material cache records include the downloaded archive SHA-256, per-channel SHA-256 and exact archive member, format, source URL, and CC0 license text. Blender reads color and emission as color textures and reads the other channels as non-color data. The ground material graph uses height or displacement to perturb normals through a Bump node.

## Verified source fixtures

Five selected model IDs and two material sets were acquired on demand. Blender 5.2.3 LTS inspected the registered model versions with disabled auto-execution and packed images.

| Asset ID | Derivative | Triangles | Packed images |
| --- | --- | ---: | ---: |
| `polyhaven-wooden_crate_01` | 2K glTF | 6,576 | 3 |
| `polyhaven-wine_barrel_01` | 2K glTF | 10,820 | 3 |
| `polyhaven-stone_01` | 2K glTF | 53,520 | 3 |
| `polyhaven-coast_rocks_01` | 1K glTF | 679,936 | 3 |
| `smithsonian-rococo-side-chair` | GLB with 4K maps | 150,000 | 2 |

`ambientcg-pavingstones036` provided five 1,024 × 1,024 maps in both JPEG and PNG, including displacement and ambient occlusion. `ambientcg-wood099` provided four JPEG maps in 2,048 × 1,024 and 4,096 × 2,048 derivatives, including displacement. Blender loaded and packed all four derivatives with sRGB on the color map and Non-Color on the data maps. The cache retained the original ZIPs and per-map manifests.

Downloaded source files and registered derivatives are stored separately. The source record in `acquired/<id>.json` shows the latest acquisition. Use `media-versions/<id>/<fingerprint>.json` for a pinned material or HDRI and `model-versions/<id>/<version>-<sha256>.json` for a pinned GLB acquisition. The default source download budget is 64 MiB, configurable with `--budget-mib`. [Asset acquisition and manual ZIP import](ACQUISITION.md)

## Other historical sources

- **Sketchfab** documents authenticated model downloads via OAuth 2.0 and temporary file URLs. The application must preserve the model-specific license, source and creator attribution. A usable automated integration requires a user-authorized account and a way to carry the required attribution to rendered or distributed outputs. [Download API integration guidelines](https://sketchfab.com/developers/download-api/guidelines), [Download request and temporary links](https://sketchfab.com/developers/download-api/downloading-models), [Developer terms](https://sketchfab.com/developers/terms)
- **Blender Studio** publishes individual production assets with their project licenses and access terms. Blender-native source files need a separate production import profile with dependency verification. [Example Studio project and license](https://studio.blender.org/projects/singularity/)
- **OpenGameArt** and **Wikimedia Commons** publish file-specific license information. Supported format and allowed reuse must be checked against the exact source file before registration. [OpenGameArt license guidance](https://opengameart.org/content/faq), [Wikimedia Commons licensing](https://commons.wikimedia.org/wiki/Commons:Licensing)
- **Open Heritage 3D** publishes dataset-specific terms and sends download links by email. Its holdings include large point-cloud and photogrammetry collections, many available for noncommercial use. [Open Heritage 3D access and licensing](https://openheritage3d.org/faq)
