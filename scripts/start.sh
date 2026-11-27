#!/usr/bin/env bash
set -euo pipefail

# Se place à la racine du projet pour retrouver le Compose et le contrat.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
local_dir="$PWD/.biaschain"
forge_dir="$local_dir/forge"
address_file="$local_dir/market-address.txt"
rpc_url="http://127.0.0.1:8545"

mkdir -p "$forge_dir/src"
if command -v flock >/dev/null 2>&1; then
    exec 9>"$local_dir/startup.lock"
    flock 9
fi

cast_anvil() {
    docker compose exec -T anvil cast "$@"
}

# Démarre Anvil et attend qu'il soit prêt.
docker compose up -d --wait anvil
if [[ "$(cast_anvil chain-id --rpc-url "$rpc_url")" != 31337 ]]; then
    printf 'Anvil must use chain ID 31337.\n' >&2
    exit 1
fi

# Compile le contrat dans Docker. Le dossier local garde les fichiers de compilation.
cp -- contracts/EnergyMarket.sol "$forge_dir/src/EnergyMarket.sol"
docker compose run --rm --no-deps -T \
    --user "$(id -u):$(id -g)" --env HOME=/work \
    --volume "$forge_dir:/work" --workdir /work \
    --entrypoint /bin/sh anvil -ec '
        forge build --use 0.8.24
        forge inspect --use 0.8.24 EnergyMarket bytecode > creation-bytecode.txt
        forge inspect --use 0.8.24 EnergyMarket deployedBytecode > deployed-bytecode.txt
    '

creation_bytecode=$(<"$forge_dir/creation-bytecode.txt")
expected_bytecode=$(<"$forge_dir/deployed-bytecode.txt")

# Si le même contrat est déjà sur la chaîne, garde son adresse.
if [[ -f "$address_file" ]]; then
    address=$(<"$address_file")
    if [[ "$address" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
        deployed_bytecode=$(cast_anvil code --rpc-url "$rpc_url" "$address")
        if [[ "$deployed_bytecode" == "$expected_bytecode" ]]; then
            printf 'EnergyMarket is already deployed at %s.\n' "$address"
            exit 0
        fi
    fi
fi

# Utilise les cinq comptes d'Anvil pour représenter les ménages.
accounts_json=$(cast_anvil rpc --rpc-url "$rpc_url" eth_accounts)
accounts=$(printf '%s' "$accounts_json" | tr -d '[]"[:space:]')
if [[ ! "$accounts" =~ ^0x[0-9a-fA-F]{40}(,0x[0-9a-fA-F]{40}){4}$ ]]; then
    printf 'Anvil must provide five test accounts.\n' >&2
    exit 1
fi

# Le premier compte installe le contrat. Chaque ménage reçoit 5 000 crédits.
constructor_args=$(cast_anvil abi-encode 'constructor(address[],uint256)' "[$accounts]" 5000)
transaction_hash=$(cast_anvil send --rpc-url "$rpc_url" --unlocked --from "${accounts%%,*}" \
    --async --create "${creation_bytecode}${constructor_args#0x}")
address=$(cast_anvil receipt --rpc-url "$rpc_url" "$transaction_hash" contractAddress)
if [[ ! "$address" =~ ^0x[0-9a-fA-F]{40}$ ]] || \
    [[ "$(cast_anvil code --rpc-url "$rpc_url" "$address")" != "$expected_bytecode" ]]; then
    printf 'EnergyMarket deployment failed.\n' >&2
    exit 1
fi

# Enregistre l'adresse que le test Python utilisera.
temporary_address_file=$(mktemp "$local_dir/market-address.XXXXXX")
printf '%s\n' "$address" > "$temporary_address_file"
mv -f -- "$temporary_address_file" "$address_file"
printf 'EnergyMarket deployed at %s. Each of the five households has 5,000 credits.\n' "$address"
