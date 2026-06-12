# Minimal rdkit stub override.
#
# The bundled rdkit-stubs package ships a malformed rdchem.pyi (parameter
# without default follows defaulted parameter — a bug in auto-generated stubs).
# These local stubs shadow the broken bundled stubs for mypy's analysis.
# riskmanager_cli no longer imports rdkit directly, but mypy still reaches it
# transitively through the (typed) dmta_cli library, so the shadow is required.
# Only the handful of symbols mypy needs to resolve are declared here.
