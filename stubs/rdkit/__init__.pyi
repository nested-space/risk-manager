# Minimal rdkit stub override.
#
# The bundled rdkit-stubs package ships a malformed rdchem.pyi (parameter
# without default follows defaulted parameter — a bug in auto-generated stubs).
# These local stubs shadow the broken bundled stubs for mypy's analysis.
# Only the symbols actually used in smiles_operations.py are declared here.
