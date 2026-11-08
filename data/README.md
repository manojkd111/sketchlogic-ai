# data/ — datasets

Directory contents are git-ignored except this README and `.gitkeep` files.

| Path | Contents |
| --- | --- |
| `raw/` | Original images/XLSX: synthetic renders, public-licensed sources, consented uploads |
| `interim/` | Cleaned or annotated intermediate data |
| `processed/` | Final train/val/test splits as `GraphDocument` JSON + image pairs |

## Consent & privacy policy (non-negotiable)

1. User uploads live in `backend/var/uploads/` and **are never copied here** unless the
   upload row has `training_consent = 1` (opt-in, default off).
2. Every sample must carry provenance: source (`synthetic` / `public:<license>` /
   `consented:<upload_id>`) and collection date. Samples without provenance are discarded.
3. If a user revokes consent, their samples are removed from `raw/`, `interim/` and
   `processed/`, and the next model version is trained without them.
4. Never upload datasets to external services (including AWS S3) without explicit approval.
