import csv
import json
from pathlib import Path

from web3 import Web3


def load_contract():
    # Le script de démarrage enregistre ces deux fichiers pour le test.
    local_dir = Path(__file__).resolve().parents[1] / ".biaschain"
    artifact_path = local_dir / "forge/out/EnergyMarket.sol/EnergyMarket.json"
    address_path = local_dir / "market-address.txt"
    if not artifact_path.is_file() or not address_path.is_file():
        raise SystemExit("Run bash scripts/start.sh from the project root first.")

    # Vérifie qu'Anvil répond sur le réseau local de test.
    web3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    if not web3.is_connected() or web3.eth.chain_id != 31337:
        raise SystemExit("The local Anvil network is unavailable.")

    # Le fichier compilé décrit les fonctions que Python peut appeler.
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    address = Web3.to_checksum_address(address_path.read_text(encoding="utf-8").strip())
    expected_bytecode = Web3.to_bytes(hexstr=artifact["deployedBytecode"]["object"])
    if web3.eth.get_code(address) != expected_bytecode:
        raise SystemExit("EnergyMarket is missing on this chain. Run bash scripts/start.sh again.")
    contract = web3.eth.contract(address=address, abi=artifact["abi"])
    return web3, contract


def submit_offer(web3, contract, *, household, household_address, operation, quantity_wh, price_per_wh):
    # Le contrat utilise 0 pour un achat et 1 pour une vente.
    side = {"buy": 0, "sell": 1}[operation]
    transaction_hash = contract.functions.submitOffer(side, quantity_wh, price_per_wh).transact(
        {"from": household_address}
    )

    # Le reçu indique si l'offre a été enregistrée et combien de gas elle a utilisé.
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)
    if receipt["status"] != 1:
        raise SystemExit("Offer submission failed.")

    # Relit l'offre dans le contrat et vérifie qu'elle correspond à ce qui a été envoyé.
    event = contract.events.OfferSubmitted().process_receipt(receipt)[0]
    offer_id = event["args"]["offerId"]
    block_number = receipt["blockNumber"]
    recorded_address, recorded_side, recorded_quantity, recorded_price = contract.functions.offers(offer_id).call(
        block_identifier=block_number
    )
    if (recorded_address.lower(), recorded_side, recorded_quantity, recorded_price) != (
        household_address.lower(),
        side,
        quantity_wh,
        price_per_wh,
    ):
        raise SystemExit("The offer recorded on-chain differs from the submitted offer.")

    # Compare les soldes à la fin du bloc précédent et à la fin du bloc de l'offre.
    previous_block = block_number - 1
    household_credits = contract.functions.creditsOf(household_address)
    credits_before = household_credits.call(block_identifier=previous_block)
    credits_after = household_credits.call(block_identifier=block_number)
    eth_before_wei = web3.eth.get_balance(household_address, block_identifier=previous_block)
    eth_after_wei = web3.eth.get_balance(household_address, block_identifier=block_number)

    # Les frais payés sont le gas utilisé multiplié par le prix d'une unité de gas.
    gas_used = receipt["gasUsed"]
    gas_price_wei = receipt["effectiveGasPrice"]
    fee_wei = gas_used * gas_price_wei
    return {
        "operation": operation,
        "household": household,
        "household_address": household_address,
        "offer_id": offer_id,
        "block_number": block_number,
        "quantity_wh": recorded_quantity,
        "price_per_wh": recorded_price,
        "credits_before": credits_before,
        "credits_after": credits_after,
        "eth_balance_before": format(Web3.from_wei(eth_before_wei, "ether"), "f"),
        "eth_balance_after": format(Web3.from_wei(eth_after_wei, "ether"), "f"),
        "gas_used": gas_used,
        "gas_price_wei": gas_price_wei,
        "fee_eth": format(Web3.from_wei(fee_wei, "ether"), "f"),
        "transaction_hash": Web3.to_hex(transaction_hash),
    }


def append_result(csv_path, result):
    # Ajoute une ligne au CSV. Les résultats des essais précédents sont aussi dans ce fichier.
    csv_path.parent.mkdir(exist_ok=True)
    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(result))
        # Écrit les noms des colonnes quand le fichier est vide.
        if csv_file.tell() == 0:
            writer.writeheader()
        writer.writerow(result)


def main():
    web3, contract = load_contract()

    # Le premier compte représente le ménage A. Il vend 2 000 Wh à 2 crédits par Wh.
    result = submit_offer(
        web3,
        contract,
        household="A",
        household_address=web3.eth.accounts[0],
        operation="sell",
        quantity_wh=2000,
        price_per_wh=2,
    )
    csv_path = Path(__file__).resolve().parent / "results" / "submit_sell_offer.csv"
    append_result(csv_path, result)

    print(f"Offer #{result['offer_id']} recorded in block {result['block_number']}")
    print(f"Offer read from the chain — {result['quantity_wh']} Wh at {result['price_per_wh']} credits per Wh")
    print(f"Gas used — {result['gas_used']}")
    print(f"Fee paid — {result['fee_eth']} test ETH")
    print(f"Result saved to {csv_path}")


if __name__ == "__main__":
    main()
