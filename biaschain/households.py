from web3 import Web3


class Household:
    # Chaque ménage a un nom et utilise une adresse Anvil pour envoyer ses offres.
    def __init__(self, name: str, address: str, contract):
        self.name = name
        self.address = Web3.to_checksum_address(address)
        self._contract = contract

    # Le contrat utilise 0 pour un achat et 1 pour une vente.
    def submit_buy_offer(self, quantity_wh: int, max_price_per_wh: int):
        return self._submit_offer(0, quantity_wh, max_price_per_wh)

    def submit_sell_offer(self, quantity_wh: int, price_per_wh: int):
        return self._submit_offer(1, quantity_wh, price_per_wh)

    # Lit le solde directement dans EnergyMarket au bloc demandé.
    def credit_balance(self, block_identifier="latest") -> int:
        return self._contract.functions.creditsOf(self.address).call(block_identifier=block_identifier)

    def _submit_offer(self, side: int, quantity_wh: int, price_per_wh: int):
        return self._contract.functions.submitOffer(side, quantity_wh, price_per_wh).transact(
            {"from": self.address}
        )
