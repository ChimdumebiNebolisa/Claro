# Claros owner-only provisioning checklist

This file records only non-secret identifiers, numeric secret versions, and
console actions that require the repository owner's accounts. It must never
contain a secret value, service-account key, owner cookie, review token, or API
key.

## Selected values

| Required value            | Selection                                                      |
| ------------------------- | -------------------------------------------------------------- |
| GCP project ID            | `claro-490122`                                                 |
| Billing                   | Enabled; billing-account details remain outside the repository |
| Deployment region         | `us-central1`                                                  |
| Private assignment bucket | `claros-assignments-490122`                                    |
| Runtime service identity  | `claros-runtime@claro-490122.iam.gserviceaccount.com`          |
| Deployment identity       | `claros-github-deploy@claro-490122.iam.gserviceaccount.com`    |

## Required Secret Manager entries

Only the version number is recorded. All values were entered through standard
input and remain server-side.

| Secret resource              | Enabled version |
| ---------------------------- | --------------- |
| `claros-cookie-secret`       | `1`             |
| `claros-review-token-secret` | `1`             |
| `claros-openai-api-key`      | `1`             |

## Owner-account console actions

- [x] In Google Cloud, select `claro-490122`, confirm billing is active, and
      keep `claros-assignments-490122` private with public access prevention.
- [x] In Secret Manager, add one enabled version to each resource above. Do not
      copy its value into GitHub, Terraform, issues, task messages, or logs.
- [x] In Google Cloud IAM, activate provider
      `projects/505797934944/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
      for repository ID `1181217565`, owner ID `130222774`, branch `main`, and the
      exact `.github/workflows/deploy.yml` workflow.
- [x] In GitHub repository settings, enable Actions/OIDC and set the non-secret
      variables `GCP_PROJECT_ID`, `GCP_REGION`,
      `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOY_SERVICE_ACCOUNT`,
      `GCP_RUNTIME_SERVICE_ACCOUNT`, `CLAROS_GCS_BUCKET`,
      `CLAROS_STAGING_SERVICE`, `CLAROS_PRODUCTION_SERVICE`, and the three
      `CLAROS_*_SECRET_VERSION` values. Both service variables are `claros`.
- [x] In GitHub Environments, create `staging` and protect `production` with
      the repository owner as a required reviewer. Production promotion remains a
      manual owner approval.

No Gate 3 provisioning value or console action remains outstanding.
