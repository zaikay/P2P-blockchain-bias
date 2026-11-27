from pathlib import Path
from uuid import uuid4

from test_submit_sell_offer import append_result, load_contract, submit_offer


def main():
    web3, contract = load_contract()
    # Prend les trois premiers comptes Anvil pour les ménages A, B et C.
    accounts = web3.eth.accounts[:3]
    if len({account.lower() for account in accounts}) < 3:
        raise SystemExit("This test requires three distinct Anvil accounts.")

    offers = [
        # Le ménage A veut vendre 2 000 Wh à 2 crédits par Wh.
        {
            "household": "A",
            "household_address": accounts[0],
            "operation": "sell",
            "quantity_wh": 2000,
            "price_per_wh": 2,
        },
        # Le ménage B veut acheter 1 000 Wh à 3 crédits par Wh au maximum.
        {
            "household": "B",
            "household_address": accounts[1],
            "operation": "buy",
            "quantity_wh": 1000,
            "price_per_wh": 3,
        },
        # Le ménage C veut acheter 500 Wh à 2 crédits par Wh au maximum.
        {
            "household": "C",
            "household_address": accounts[2],
            "operation": "buy",
            "quantity_wh": 500,
            "price_per_wh": 2,
        },
    ]

    csv_path = Path(__file__).resolve().parent / "results" / "submit_sell_and_buy_offers.csv"
    # Les trois lignes d'un même test auront le même identifiant.
    run_id = uuid4().hex

    for offer in offers:
        result = submit_offer(web3, contract, **offer)
        # Garde le résultat de chaque offre dès qu'elle est enregistrée.
        append_result(csv_path, {"run_id": run_id, **result})
        print(f"Household {result['household']} — offer #{result['offer_id']} ({result['operation']})")

    print(f"Results saved to {csv_path}")


if __name__ == "__main__":
    main()
