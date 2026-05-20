import requests

UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"


def get_uniprot_data(gene_symbol: str) -> dict:
    """
    Fetch the reviewed (Swiss-Prot) human protein entry for a gene symbol.
    Returns structured protein info or {"error": ...} if not found.
    """
    try:
        resp = requests.get(
            UNIPROT_SEARCH,
            params={
                "query": f"gene_exact:{gene_symbol} AND organism_id:9606 AND reviewed:true",
                "format": "json",
                "size": 1,
                "fields": "accession,protein_name,gene_names,cc_function,cc_subcellular_location,cc_disease,ft_transmem,ft_signal",
            },
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            # Retry without gene_exact (some symbols don't match exactly)
            resp = requests.get(
                UNIPROT_SEARCH,
                params={
                    "query": f"gene:{gene_symbol} AND organism_id:9606 AND reviewed:true",
                    "format": "json",
                    "size": 1,
                    "fields": "accession,protein_name,gene_names,cc_function,cc_subcellular_location,cc_disease,ft_transmem,ft_signal",
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        if not results:
            return {"error": f"No reviewed UniProt entry found for gene '{gene_symbol}' in human."}

        entry = results[0]
        accession = entry.get("primaryAccession", "")

        # Protein name
        prot_desc = entry.get("proteinDescription", {})
        recommended = prot_desc.get("recommendedName", {})
        protein_name = recommended.get("fullName", {}).get("value", "")

        # Function
        function_text = ""
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                texts = comment.get("texts", [])
                if texts:
                    function_text = texts[0].get("value", "")[:600]
                    break

        # Subcellular location
        locations = []
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for loc in comment.get("subcellularLocations", []):
                    loc_val = loc.get("location", {}).get("value", "")
                    if loc_val:
                        locations.append(loc_val)

        # Disease associations
        diseases = []
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "DISEASE":
                disease = comment.get("disease", {})
                name = disease.get("diseaseId", "") or disease.get("diseaseName", "")
                if name:
                    diseases.append(name)

        # Transmembrane / signal peptide — relevant for biologic accessibility
        features = entry.get("features", [])
        has_transmembrane = any(f.get("type") == "Transmembrane" for f in features)
        has_signal_peptide = any(f.get("type") == "Signal peptide" for f in features)

        return {
            "accession": accession,
            "protein_name": protein_name,
            "function": function_text,
            "subcellular_locations": locations,
            "disease_associations": diseases,
            "has_transmembrane_domain": has_transmembrane,
            "has_signal_peptide": has_signal_peptide,
            "uniprot_url": f"https://www.uniprot.org/uniprotkb/{accession}",
        }

    except Exception as e:
        return {"error": str(e)}


def format_for_context(data: dict) -> str:
    """Convert UniProt data into a readable string for agent context."""
    if "error" in data:
        return f"UniProt: {data['error']}"

    lines = [
        f"## UniProt Profile: {data['protein_name']} ({data['accession']})",
        f"Function: {data['function']}",
        "",
        f"Subcellular location: {', '.join(data['subcellular_locations']) or 'unknown'}",
        f"Transmembrane domain: {'Yes — intracellular portions not accessible to antibodies' if data['has_transmembrane_domain'] else 'No'}",
        f"Signal peptide: {'Yes — likely secreted or membrane-targeted' if data['has_signal_peptide'] else 'No'}",
    ]

    if data["disease_associations"]:
        lines += ["", "Disease associations in UniProt:"]
        for d in data["disease_associations"][:5]:
            lines.append(f"- {d}")

    lines.append(f"\nSource: {data['uniprot_url']}")
    return "\n".join(lines)
