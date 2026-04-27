import sys
import os
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")
API_KEY = os.getenv("STEAM_API_KEY")

if not API_KEY:
    print("Error: no se encontró STEAM_API_KEY en el archivo .env")
    sys.exit(1)

STEAM_API_BASE = "https://api.steampowered.com"


def resolve_vanity_url(vanity_name: str) -> str | None:
    """Convierte un nombre de usuario de Steam en SteamID64."""
    url = f"{STEAM_API_BASE}/ISteamUser/ResolveVanityURL/v1/"
    params = {"key": API_KEY, "vanityurl": vanity_name}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        result = response.json().get("response", {})
        if result.get("success") == 1:
            return result["steamid"]
        else:
            print(f"No se encontró el usuario '{vanity_name}'.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error al resolver el nombre de usuario: {e}")
        return None


def fetch_game_name(app_id: str) -> tuple[str, str]:
    """Obtiene el nombre de un juego a partir de su app_id."""
    url = f"https://store.steampowered.com/api/appdetails"
    params = {"appids": app_id, "filters": "basic"}

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        name = (data
                .get(app_id, {})
                .get("data", {})
                .get("name", f"App {app_id}"))
        return app_id, name
    except Exception:
        return app_id, f"App {app_id}"


def get_wishlist(steam_id: str) -> list[dict]:
    """Obtiene la wishlist de un usuario usando su SteamID64."""
    url = f"{STEAM_API_BASE}/IWishlistService/GetWishlist/v1"
    params = {"key": API_KEY, "steamid": steam_id}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print("Error: la petición tardó demasiado.")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP: {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error de red: {e}")
        return []

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        print("Steam no devolvió una respuesta válida.")
        print(f"Respuesta recibida: {response.text[:300]}")
        return []

    items = data.get("response", {}).get("items", [])

    if not items:
        print("La wishlist está vacía o el perfil es privado.")
        return []

    # Obtener nombres en paralelo para mayor velocidad
    print(f"Obteniendo nombres de {len(items)} juegos...")
    app_ids = [str(item.get("appid", "")) for item in items]
    names = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_game_name, aid): aid for aid in app_ids}
        for future in as_completed(futures):
            app_id, name = future.result()
            names[app_id] = name

    games = []
    for item in items:
        app_id = str(item.get("appid", ""))
        games.append({
            "app_id":   app_id,
            "title":    names.get(app_id, f"App {app_id}"),
            "priority": item.get("priority", 0),
        })

    games.sort(key=lambda g: g["priority"])
    return games


if __name__ == "__main__":
    user_input = input("Introduce el nombre de usuario o SteamID64: ").strip()

    if not user_input:
        print("Error: debes introducir un nombre de usuario o SteamID64.")
        sys.exit(1)

    # Detectar si es SteamID64 (número de 17 dígitos) o nombre de usuario
    if user_input.isdigit() and len(user_input) == 17:
        steam_id = user_input
    else:
        print(f"Resolviendo '{user_input}'...")
        steam_id = resolve_vanity_url(user_input)
        if not steam_id:
            sys.exit(1)

    print(f"Obteniendo wishlist para SteamID: {steam_id}...\n")
    wishlist = get_wishlist(steam_id)

    if not wishlist:
        sys.exit(0)

    # Mostrar resultados
    col = 45
    print(f"{'#':<5} {'Título':<{col}} {'App ID'}")
    print("─" * (5 + col + 12))
    for i, game in enumerate(wishlist, 1):
        title = game['title']
        if len(title) > col - 2:
            title = title[:col - 5] + "..."
        print(f"{i:<5} {title:<{col}} {game['app_id']}")

    print(f"\nTotal: {len(wishlist)} juegos en la wishlist.")