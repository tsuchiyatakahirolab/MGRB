# Export receipt verification

`mgrb verify` remains generic provenance/hash verification. It does not authenticate
an official publisher. `mgrb verify-official` implements the separate offline
receipt contract. Install the optional `authenticity` extra.

```sh
mgrb verify-official map.png --receipt map.png.receipt.json
mgrb verify-official map.png.receipt.json --file map.png
mgrb verify-official map.png --development-key development-public.json
```

No private signing material or signing operation is included in public Core.
The production trust registry is deliberately empty until owner-approved key
commissioning. Caller-supplied keys can validate development receipts only;
they cannot establish Official MGRB trust. A fork can edit its own verifier, but
cannot create signatures accepted by the canonical verifier's trusted keys.

Receipts contain only bounded ASCII string fields: schema, purpose, algorithm,
export_id, build_id, mgrb_version, created_at, file_sha256, build_spec_sha256,
source_manifest_sha256, watermark_payload_hash, signing_key_id and signature.
Schema is `mgrb-export-receipt-1`; purpose is `DEVELOPMENT_NOT_OFFICIAL` or
`OFFICIAL_MGRB`. Ed25519 signs the domain prefix `MGRB-EXPORT-RECEIPT/v1` followed
by a zero byte and compact, lexicographically sorted JSON of all fields except
signature. ASCII strings only, no floats/nesting, duplicate or unknown members.
Signature/public-key encodings are standard base64. Hashes are SHA-256 of exact bytes.

Canonicalization is this restricted contract, not arbitrary JSON/JCS. Creation
time is a signer's assertion, not a trusted timestamp. Future production keys
need reviewed validity, rotation and revocation records; offline verification
can only know the revocations shipped with its trust registry.

Results distinguish official valid/absent/invalid and file hash mismatch. Explicit
development results never set `official=true`. Receipt-only verification returns
`*_FILE_UNCHECKED`; it does not authenticate a supplied image. Verifying the file
does not independently reconstruct the Build Spec or upstream source manifest.
Their signed hashes allow those documents to be checked when independently supplied.

Watermark recovery and visible branding never determine verification status.
Recompression, cropping or metadata stripping can change the file hash while
the detached receipt still verifies the original bytes. Receipt lookup must not
fetch arbitrary URLs or expose user/dataset identities.
