import csv
import json
from pathlib import Path

from web3 import Web3


def main():
    # Le script de démarrage enregistre ces deux fichiers pour le test.
    dossier_local = Path(__file__).resolve().parents[1] / ".biaschain"
    fichier = dossier_local / "forge/out/EnergyMarket.sol/EnergyMarket.json"
    fichier_adresse = dossier_local / "market-address.txt"
    if not fichier.is_file() or not fichier_adresse.is_file():
        raise SystemExit("Lance d'abord bash scripts/start.sh depuis le dossier du projet.")

    # Vérifie qu'Anvil répond sur le réseau local de test.
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    if not w3.is_connected() or w3.eth.chain_id != 31337:
        raise SystemExit("Le réseau Anvil local est introuvable.")

    # Le fichier compilé décrit les fonctions que Python peut appeler.
    contrat_compile = json.loads(fichier.read_text(encoding="utf-8"))
    adresse = Web3.to_checksum_address(fichier_adresse.read_text(encoding="utf-8").strip())
    code_attendu = Web3.to_bytes(hexstr=contrat_compile["deployedBytecode"]["object"])
    if w3.eth.get_code(adresse) != code_attendu:
        raise SystemExit("Le contrat est introuvable sur cette chaîne. Relance bash scripts/start.sh.")
    contrat = w3.eth.contract(address=adresse, abi=contrat_compile["abi"])

    # Le premier compte représente le ménage A. Il vend 2 000 Wh à 2 crédits par Wh.
    # Le premier nombre vaut 1 pour une vente.
    menage_a = w3.eth.accounts[0]
    transaction = contrat.functions.submitOffer(1, 2000, 2).transact({"from": menage_a})

    # Le reçu indique si l'offre a été enregistrée et combien de gas elle a utilisé.
    recu = w3.eth.wait_for_transaction_receipt(transaction)
    if recu["status"] != 1:
        raise SystemExit("L'envoi de l'offre a échoué.")

    # Récupère le numéro dans le reçu, puis relit l'offre dans le contrat.
    evenement = contrat.events.OfferSubmitted().process_receipt(recu)[0]
    numero = evenement["args"]["offerId"]
    bloc = recu["blockNumber"]
    _, _, quantite, prix = contrat.functions.offers(numero).call(block_identifier=bloc)

    # Compare les soldes à la fin du bloc précédent et à la fin du bloc de l'offre.
    bloc_avant = bloc - 1
    credits_du_menage = contrat.functions.creditsOf(menage_a)
    credits_avant = credits_du_menage.call(block_identifier=bloc_avant)
    credits_apres = credits_du_menage.call(block_identifier=bloc)
    eth_avant_wei = w3.eth.get_balance(menage_a, block_identifier=bloc_avant)
    eth_apres_wei = w3.eth.get_balance(menage_a, block_identifier=bloc)

    # Les frais payés sont le gas utilisé multiplié par le prix d'une unité de gas.
    gas_utilise = recu["gasUsed"]
    prix_gas_wei = recu["effectiveGasPrice"]
    frais_wei = gas_utilise * prix_gas_wei
    resultat = {
        "operation": "vente",
        "menage": "A",
        "adresse_menage": menage_a,
        "numero_offre": numero,
        "bloc": bloc,
        "quantite_wh": quantite,
        "prix_par_wh": prix,
        "solde_credits_avant": credits_avant,
        "solde_credits_apres": credits_apres,
        "solde_eth_avant": format(Web3.from_wei(eth_avant_wei, "ether"), "f"),
        "solde_eth_apres": format(Web3.from_wei(eth_apres_wei, "ether"), "f"),
        "gas_utilise": gas_utilise,
        "prix_gas_wei": prix_gas_wei,
        "frais_eth": format(Web3.from_wei(frais_wei, "ether"), "f"),
        "hash_transaction": Web3.to_hex(transaction),
    }

    # Crée test/results au besoin et ajoute une ligne au CSV à chaque essai réussi.
    dossier_resultats = Path(__file__).resolve().parent / "results"
    dossier_resultats.mkdir(exist_ok=True)
    chemin_csv = dossier_resultats / "submit_sell_offer.csv"

    with chemin_csv.open("a", encoding="utf-8", newline="") as fichier_csv:
        csv_transactions = csv.DictWriter(fichier_csv, fieldnames=list(resultat))
        # Écrit les noms des colonnes quand le fichier est vide.
        if fichier_csv.tell() == 0:
            csv_transactions.writeheader()
        csv_transactions.writerow(resultat)

    print(f"Offre n° {numero} enregistrée dans le bloc {bloc}")
    print(f"Offre relue sur la chaîne — {quantite} Wh à {prix} crédits par Wh")
    print(f"Gas utilisé — {gas_utilise}")
    print(f"Frais payés — {resultat['frais_eth']} ETH de test")
    print(f"Résultat enregistré dans {chemin_csv}")


if __name__ == "__main__":
    main()
