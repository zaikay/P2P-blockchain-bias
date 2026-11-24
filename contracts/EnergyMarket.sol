// SPDX-License-Identifier: MIT
// Le contrat utilise Solidity 0.8.24 ou une version plus récente de la série 0.8.
pragma solidity ^0.8.24;

// Contrat qui enregistre les offres et règle les échanges d'énergie.
contract EnergyMarket {
    // 0 veut dire achat. 1 veut dire vente.
    enum Side {
        Buy,
        Sell
    }

    // Une offre indique qui achète ou vend, la quantité restante et le prix de 1 Wh.
    struct Offer {
        address household;
        Side side;
        uint256 remainingWh;
        uint256 pricePerWh;
    }

    // Indique si une adresse est inscrite comme ménage.
    mapping(address => bool) public isHousehold;
    // Nombre de crédits dont dispose chaque ménage.
    mapping(address => uint256) public creditsOf;
    // Liste des offres. La première a le numéro 0, la suivante le numéro 1.
    Offer[] public offers;

    // Message enregistré sur la chaîne quand un ménage envoie une offre.
    event OfferSubmitted(
        uint256 indexed offerId,
        address indexed household,
        Side side,
        uint256 quantityWh,
        uint256 pricePerWh
    );
    // Message enregistré sur la chaîne quand un échange est terminé.
    event TradeSettled(
        uint256 indexed sellOfferId,
        uint256 indexed buyOfferId,
        address indexed seller,
        address buyer,
        uint256 quantityWh,
        uint256 pricePerWh,
        uint256 totalCredits
    );

    // Au démarrage, on donne les adresses des ménages et leurs crédits de départ.
    constructor(address[] memory households, uint256 initialCredits) {
        require(households.length >= 2, "At least two households are required");
        require(initialCredits > 0, "Initial credits must be positive");
        // Vérifie qu'un seul compte pourrait contenir tous les crédits.
        require(initialCredits <= type(uint256).max / households.length, "Total credits exceed limit");

        // Inscrit chaque adresse une seule fois et lui donne ses crédits de départ.
        for (uint256 i; i < households.length; ++i) {
            address household = households[i];
            require(household != address(0) && !isHousehold[household], "Invalid or duplicate household");
            isHousehold[household] = true;
            creditsOf[household] = initialCredits;
        }
    }

    // Le prix est en crédits par Wh. L'acheteur donne son maximum et le vendeur son prix demandé.
    function submitOffer(Side side, uint256 quantityWh, uint256 pricePerWh) external returns (uint256 offerId) {
        // msg.sender est le compte qui a envoyé l'offre. Il doit être inscrit.
        require(isHousehold[msg.sender], "Unknown household");
        require(quantityWh > 0, "Quantity must be positive");
        require(pricePerWh > 0, "Price must be positive");

        // L'acheteur doit pouvoir payer toute la quantité au prix qu'il a indiqué.
        if (side == Side.Buy) {
            require(quantityWh <= creditsOf[msg.sender] / pricePerWh, "Insufficient credits");
        }

        // Si la liste contient déjà 2 offres, la suivante prend le numéro 2.
        offerId = offers.length;
        offers.push(Offer({household: msg.sender, side: side, remainingWh: quantityWh, pricePerWh: pricePerWh}));
        // Le script Python retrouve le numéro de l'offre dans le reçu de la transaction.
        emit OfferSubmitted(offerId, msg.sender, side, quantityWh, pricePerWh);
    }

    // On donne le numéro de la vente et celui de l'achat pour régler l'échange.
    function settle(uint256 sellOfferId, uint256 buyOfferId) external {
        // Vérifie que les deux offres existent.
        require(sellOfferId < offers.length && buyOfferId < offers.length, "Unknown offer");

        // Avec storage, les changements apportés aux offres sont gardés sur la chaîne.
        Offer storage sellOffer = offers[sellOfferId];
        Offer storage buyOffer = offers[buyOfferId];
        // Il faut une vente et un achat avec des Wh encore disponibles.
        require(sellOffer.side == Side.Sell && buyOffer.side == Side.Buy, "Expected a sell and a buy offer");
        require(sellOffer.remainingWh > 0 && buyOffer.remainingWh > 0, "Offer already filled");

        // L'acheteur et le vendeur doivent être deux ménages différents.
        address seller = sellOffer.household;
        address buyer = buyOffer.household;
        require(seller != buyer, "Households cannot trade with themselves");

        // Le vendeur fixe le prix de l'échange si l'acheteur accepte de payer au moins ce prix.
        uint256 tradePricePerWh = sellOffer.pricePerWh;
        require(buyOffer.pricePerWh >= tradePricePerWh, "Buy price is below sell price");

        // On échange la plus petite quantité. Si un ménage vend 2 000 Wh et que
        // l'autre en achète 1 000, on échange 1 000 Wh et il en reste 1 000 à vendre.
        uint256 quantityWh = sellOffer.remainingWh < buyOffer.remainingWh
            ? sellOffer.remainingWh
            : buyOffer.remainingWh;

        // Vérifie que l'acheteur a encore assez de crédits pour payer l'échange.
        require(quantityWh <= creditsOf[buyer] / tradePricePerWh, "Insufficient credits");
        // Le prix total est la quantité échangée multipliée par le prix de 1 Wh.
        uint256 totalCredits = quantityWh * tradePricePerWh;

        // Retire la quantité échangée des deux offres.
        sellOffer.remainingWh -= quantityWh;
        buyOffer.remainingWh -= quantityWh;
        // Enlève les crédits à l'acheteur et les ajoute au vendeur.
        creditsOf[buyer] -= totalCredits;
        creditsOf[seller] += totalCredits;

        // Le script Python pourra lire ce message et afficher l'échange.
        emit TradeSettled(sellOfferId, buyOfferId, seller, buyer, quantityWh, tradePricePerWh, totalCredits);
    }
}
