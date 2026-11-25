# Sketchfab assets in ATLAS

3D models provided by Sketchfab. ATLAS searches the public Data API, normalizes downloadable static candidates, and retains creator credit, model URLs, license versions, and available thumbnail references. The default search covers medieval architecture, ruins, castles, historical furniture and artifacts, and landscapes. The catalog accepts CC0 1.0 and CC BY 4.0 based on the Sketchfab license identity. [Data API](https://docs.sketchfab.com/data-api/v3/index.html) · [Sketchfab license records](https://api.sketchfab.com/v3/licenses) · [Download API guidelines](https://sketchfab.com/developers/download-api/guidelines)

## Discover and review

```powershell
atlas assets sync sketchfab
atlas assets sync sketchfab --query "castle courtyard" --category architecture --tag photogrammetry --pages 2
atlas assets catalog castle --provider sketchfab
```

Use the provider's slugs for `--category` and `--tag` during sync. Repeat either flag to require multiple slugs. ATLAS searches up to 24 results per page and one to five pages per query and license. It follows only cursor values from the API. Catalog dimensions, mesh counts, and quality still require inspection. Search metadata and thumbnails describe candidates.

## Authorize a download

1. Register an application with Sketchfab for the **Authorization Code** grant. Register a loopback redirect such as `http://127.0.0.1:8412/sketchfab-callback`. [Sketchfab OAuth setup](https://sketchfab.com/developers/oauth)
2. Load the registered values into the current ATLAS process environment with your local secret manager or shell's hidden prompt. Use `ATLAS_SKETCHFAB_CLIENT_ID`, `ATLAS_SKETCHFAB_CLIENT_SECRET`, and `ATLAS_SKETCHFAB_REDIRECT_URI`. The redirect must match the registered address, including port and path. ATLAS accepts `127.0.0.1` or `localhost` with an explicit port between 1024 and 65535 and a single path component.
3. Find a candidate in the catalog, review the credit and source, then run the download command. Authorize ATLAS in the browser using your Sketchfab account. To check the grant before selecting an asset, run `atlas assets auth sketchfab --login`.

```powershell
$asset = "sketchfab-REPLACE-WITH-MODEL-UID"
atlas assets download $asset --sketchfab-login --budget-mib 96
atlas assets inspect $asset --version 1
```

Use the version returned by `download` for inspection. Registration validates the GLB container and leaves the asset pending. Blender inspection is required before it can enter a production scene. The download budget defaults to 64 MiB with an archive cap of 128 MiB. ATLAS loads the documented `scene.gltf` ZIP layout, embeds its binary buffer and PNG/JPEG textures, and applies the existing static GLB checks. [Official archive format](https://sketchfab.com/developers/download-api/downloading-models)

## Environment-only automation

For a user-authorized unattended run, inject an existing Sketchfab OAuth bearer token through `ATLAS_SKETCHFAB_ACCESS_TOKEN`. Supply its UTC Unix expiry in seconds in `ATLAS_SKETCHFAB_TOKEN_EXPIRES_AT` when known. To refresh an expired access token or retry a rejected token once, supply `ATLAS_SKETCHFAB_REFRESH_TOKEN` together with the registered `ATLAS_SKETCHFAB_CLIENT_ID` and `ATLAS_SKETCHFAB_CLIENT_SECRET`. Invoke `atlas assets auth sketchfab` to check the grant or run `atlas assets download $asset` without the interactive flag. Your secret manager should provision current credentials for each invocation. ATLAS retains refreshed tokens in the current process and clears the browser login context on exit. [Sketchfab token renewal](https://sketchfab.com/developers/oauth)

Keep secret inputs in the current process environment or a local vault. Avoid pasting credentials into chat, command arguments, shell history, or repository files. ATLAS sends the bearer token only to the documented Sketchfab API endpoints. The archive request uses the separately issued temporary link without an authorization header. ATLAS discards the signed URL and verifies cached bytes against their recorded size and SHA-256. The production registry can reuse an inspected local asset through its pinned version.

The acquisition record and production provenance include the creator, source URL, license text, and GLB conversion credit. Keep the credit available when publishing derived work, especially with CC BY models. [Sketchfab API terms](https://sketchfab.com/developers/terms) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
