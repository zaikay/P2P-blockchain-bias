import csv
from pathlib import Path

from web3 import Web3
from web3.exceptions import TransactionNotFound

from test_submit_sell_offer import append_result, load_contract, load_households


def load_offer_pair(results_dir):
    # Reprend les offres de A et B dans le dernier test de publication.
    offers_path = results_dir / "submit_sell_and_buy_offers.csv"
    if not offers_path.is_file():
        raise SystemExit("Run test_submit_sell_and_buy_offers.py first.")
    with offers_path.open(encoding="utf-8", newline="") as offers_file:
        rows = list(csv.DictReader(offers_file))
    if not rows:
        raise SystemExit("The offer CSV has no results. Run the offer test first.")

    run_id = rows[-1]["run_id"]
    latest = {(row["household"], row["operation"]): row for row in rows if row["run_id"] == run_id}
    if ("A", "sell") not in latest or ("B", "buy") not in latest:
        raise SystemExit("The latest run must contain a sell offer from A and a buy offer from B.")
    return run_id, latest[("A", "sell")], latest[("B", "buy")]


def verify_offer(web3, contract, household, row, side):
    # L'identifiant seul peut être réutilisé si Anvil a redémarré. On vérifie aussi le reçu.
    try:
        receipt = web3.eth.get_transaction_receipt(row["transaction_hash"])
    except TransactionNotFound:
        raise SystemExit("The saved offers are missing on Anvil. Run the offer test again.") from None

    offer_id = int(row["offer_id"])
    events = contract.events.OfferSubmitted().process_receipt(receipt)
    expected = {
        "offerId": offer_id,
        "household": household.address,
        "side": side,
        "quantityWh": int(row["quantity_wh"]),
        "pricePerWh": int(row["price_per_wh"]),
    }
    if receipt["status"] != 1 or len(events) != 1 or events[0]["address"] != contract.address:
        raise SystemExit(f"The receipt for offer #{offer_id} could not be verified.")
    if dict(events[0]["args"]) != expected:
        raise SystemExit(f"The saved data for offer #{offer_id} differs from the chain.")

    current_offer = contract.functions.offers(offer_id).call()
    if tuple(current_offer) != (household.address, side, expected["quantityWh"], expected["pricePerWh"]):
        raise SystemExit(f"Offer #{offer_id} has changed. Run the offer test again.")

    return offer_id, expected["quantityWh"], expected["pricePerWh"]


def main():
    results_dir = Path(__file__).resolve().parent / "results"
    run_id, sell_row, buy_row = load_offer_pair(results_dir)
    web3, contract = load_contract()
    seller, buyer = load_households(web3, contract, ("A", "B"))
    sell_id, sell_quantity, sell_price = verify_offer(web3, contract, seller, sell_row, 1)
    buy_id, buy_quantity, buy_price = verify_offer(web3, contract, buyer, buy_row, 0)
    if buy_price < sell_price:
        raise SystemExit("The buyer's price is below the seller's price.")

    expected_quantity = min(sell_quantity, buy_quantity)
    expected_total = expected_quantity * sell_price

    # L'acheteur appelle settle et paie les frais d'envoi en ETH de test.
    transaction = contract.functions.settle(sell_id, buy_id).transact({"from": buyer.address})
    transaction_hash = Web3.to_hex(transaction)
    print(f"Settlement transaction — {transaction_hash}", flush=True)
    receipt = web3.eth.wait_for_transaction_receipt(transaction)
    if receipt["status"] != 1:
        raise SystemExit("Settlement failed on Anvil.")

    events = contract.events.TradeSettled().process_receipt(receipt)
    if len(events) != 1 or events[0]["address"] != contract.address:
        raise SystemExit("Expected one TradeSettled event from EnergyMarket.")
    trade = dict(events[0]["args"])

    # Lit les soldes avant et après le bloc du règlement.
    block_number = receipt["blockNumber"]
    previous_block = block_number - 1
    seller_before = seller.credit_balance(block_identifier=previous_block)
    seller_after = seller.credit_balance(block_identifier=block_number)
    buyer_before = buyer.credit_balance(block_identifier=previous_block)
    buyer_after = buyer.credit_balance(block_identifier=block_number)
    sell_remaining = contract.functions.offers(sell_id).call(block_identifier=block_number)[2]
    buy_remaining = contract.functions.offers(buy_id).call(block_identifier=block_number)[2]
    buyer_eth_before = web3.eth.get_balance(buyer.address, block_identifier=previous_block)
    buyer_eth_after = web3.eth.get_balance(buyer.address, block_identifier=block_number)
    gas_used = receipt["gasUsed"]
    gas_price_wei = receipt["effectiveGasPrice"]
    fee_wei = gas_used * gas_price_wei

    # Vérifie l'échange, le transfert de crédits et le reste de chaque offre.
    passed = (
        trade == {
            "sellOfferId": sell_id,
            "buyOfferId": buy_id,
            "seller": seller.address,
            "buyer": buyer.address,
            "quantityWh": expected_quantity,
            "pricePerWh": sell_price,
            "totalCredits": expected_total,
        }
        and seller_after - seller_before == expected_total
        and buyer_before - buyer_after == expected_total
        and sell_remaining == sell_quantity - expected_quantity
        and buy_remaining == buy_quantity - expected_quantity
        and buyer_eth_before - buyer_eth_after == fee_wei
    )

    csv_path = results_dir / "settle_trade.csv"
    append_result(csv_path, {
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "seller": seller.name,
        "seller_address": trade["seller"],
        "buyer": buyer.name,
        "buyer_address": trade["buyer"],
        "sell_offer_id": trade["sellOfferId"],
        "buy_offer_id": trade["buyOfferId"],
        "quantity_wh": trade["quantityWh"],
        "price_per_wh": trade["pricePerWh"],
        "total_credits": trade["totalCredits"],
        "seller_credits_before": seller_before,
        "seller_credits_after": seller_after,
        "buyer_credits_before": buyer_before,
        "buyer_credits_after": buyer_after,
        "sell_quantity_before_wh": sell_quantity,
        "sell_quantity_after_wh": sell_remaining,
        "buy_quantity_before_wh": buy_quantity,
        "buy_quantity_after_wh": buy_remaining,
        "buyer_eth_before": format(Web3.from_wei(buyer_eth_before, "ether"), "f"),
        "buyer_eth_after": format(Web3.from_wei(buyer_eth_after, "ether"), "f"),
        "gas_used": gas_used,
        "gas_price_wei": gas_price_wei,
        "fee_eth": format(Web3.from_wei(fee_wei, "ether"), "f"),
        "block_number": block_number,
        "transaction_hash": transaction_hash,
    })
    if not passed:
        raise SystemExit(f"Settlement verification failed. See {csv_path}.")

    print(f"Trade read from block {block_number} — {trade['quantityWh']} Wh for {trade['totalCredits']} credits")
    print(f"Seller {seller.name} credits — {seller_before} to {seller_after}")
    print(f"Buyer {buyer.name} credits — {buyer_before} to {buyer_after}")
    print(f"Remaining Wh — sale {sell_remaining}, purchase {buy_remaining}")
    print(f"Gas used — {gas_used}. Result saved to {csv_path}")


if __name__ == "__main__":
    main()
