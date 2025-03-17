import os
import urllib.request
import urllib.parse
import json
import re
from html import unescape


def create_env_file(filepath=".env"):
    """Create a .env file by asking the user for the necessary environment variables."""
    print("The access to the Zotero API was not configured yet.")
    print()

    # Ask the user for the parameters
    print(
        "Please create a Zotero API Key here with full read permissions to the library to access if you do not have one: https://www.zotero.org/settings/security"
    )
    zotero_api_key = input("Enter your Zotero API Key: ")
    print()

    zotero_library_type = ""
    while zotero_library_type not in ["user", "group"]:
        print("Please select the type of the library you want to access.")
        zotero_library_type = input("Enter your Zotero Library Type (user/group): ")
        print()

    if zotero_library_type == "user":
        print(
            "Please lookup your user id here: https://www.zotero.org/settings/security"
        )
        zotero_library_id = input("Enter your Zotero User ID: ")
    elif zotero_library_type == "group":
        print(
            "Please click on your group library here: https://www.zotero.org/mylibrary"
        )
        print("Then copy the numeric ID that comes in the URL after groups/")
        zotero_library_id = input("Enter your Zotero Group Library ID: ")
    print()

    # Prepare the content to be written to the environment file
    env_content = f"""# Your Zotero API credentials

# Replace with your Zotero API Key (this can be generated in the security settings: https://www.zotero.org/settings/security)
# This is in the following format: 1234567890abcdefghijklmn
ZOTERO_API_KEY={zotero_api_key}

# Replace with your Zotero library ID
# This is in the following format: 1234567
ZOTERO_LIBRARY_ID={zotero_library_id}

# Use 'user' for personal library, 'group' for group libraries
ZOTERO_LIBRARY_TYPE={zotero_library_type}
"""

    # Write the content to the file
    with open(filepath, "w") as file:
        file.write(env_content)
    print(f"Environment file created at: {filepath}")


def load_env_file(filepath=".env"):
    """Load environment variables from a .env file into a dictionary"""
    # Check if the file exists
    if not os.path.exists(filepath):
        create_env_file(filepath)

    env_dict = {}

    with open(filepath, "r") as file:
        for line in file:
            line = line.strip()  # Remove any leading/trailing whitespace
            if line and not line.startswith("#"):  # Ignore empty lines and comments
                key, value = line.split("=", 1)  # Split at first '='
                env_dict[key] = value  # Set the environment variable

    return env_dict


def set_env_file_invalid(filepath=".env"):
    """Add a parameter that marks the env file as invalid"""

    with open(filepath, "a") as file:
        invalid_content = """
# Please remove the line below if you adjust this file manually
INVALID=True
"""
        file.write(invalid_content)


def is_env_file_invalid(filepath=".env") -> bool:
    """Check if the env file was marked as invalid"""
    is_invalid = False
    with open(filepath, "r") as file:
        for line in file:
            if line == "INVALID=True":
                is_invalid = True

    return is_invalid


def fetch_items(base_url, api_key):
    """Function to fetch Zotero items (metadata + annotations) from the API"""
    items = []
    url = base_url
    params = {
        "format": "json",
    }
    query_string = urllib.parse.urlencode(params)

    while url:
        if query_string:
            if "?" in url:
                full_url = f"{url}&{query_string}"
            else:
                full_url = f"{url}?{query_string}"
        else:
            full_url = url
        req = urllib.request.Request(full_url, headers={"Zotero-API-Key": api_key})
        print(f"Querying {full_url}")

        try:
            # Make the request
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    items += json.load(response)
                    # If there are more pages, the response will contain a 'link' to the next page
                    link_header = response.headers.get("Link", "")
                    url = None

                    # Look for the 'next' page link in the 'Link' header
                    for link in link_header.split(","):
                        if 'rel="next"' in link:
                            # Extract the URL inside the angle brackets
                            url = link.split(";")[0].strip()[1:-1]
                            break
                else:
                    print(f"Error fetching data: {response.status}")
                    print(f"Response content: {response.read().decode()}")

                    if response.status == 403:
                        set_env_file_invalid()
                    break

        except urllib.error.URLError as e:
            print(f"Request failed: {e}")
            break

    print("Finished querying Zotero API")
    return items


def create_item_mapping(items):
    """Function to create a mapping of item keys to their titles, authors and parentItems"""
    item_mapping = {}
    for item in items:
        item_data = item.get("data", {})
        item_key = item_data.get("key")
        item_title = item_data.get("title")
        meta = item.get("meta")
        authors = meta.get("creatorSummary", "")
        parent_item = item_data.get("parentItem", "")
        item_mapping[item_key] = {
            "itemTitle": item_title,
            "authors": authors,
            "parentItem": parent_item,
        }
    return item_mapping


def get_parent_info(parent_item_key, item_mapping):
    while parent_item_key:
        parent_info = item_mapping.get(parent_item_key)
        if not parent_info:
            return None
        title = parent_info.get("itemTitle", "")
        authors = parent_info.get("authors", "")
        parent_item_key = parent_info.get("parentItem")
    return title, authors


def extract_annotations(items, item_mapping):
    """Function to extract annotations from the items"""
    annotations = []
    print("Extracting annotations...")
    for item in items:
        item_data = item.get("data", {})  # Access the 'data' field
        if item_data.get("itemType") == "annotation":  # Only process annotations
            parent_item_key = item_data.get("parentItem")
            parent_info = get_parent_info(parent_item_key, item_mapping)
            if parent_info:
                parent_item_title, parent_item_authors = parent_info
                annotation = {
                    "key": item_data.get("key"),
                    "parentItem": {
                        "key": parent_item_key,
                        "title": parent_item_title,
                        "authors": parent_item_authors,
                    },
                    "annotationText": item_data.get("annotationText"),
                    "annotationComment": item_data.get("annotationComment"),
                    "annotationColor": item_data.get("annotationColor"),
                }
                annotations.append(annotation)
    print("Finished extracting annotations")
    return annotations


def extract_notes(items, item_mapping):
    """Function to extract notes from the items"""
    notes = []
    print("Extracting notes...")
    for item in items:
        item_data = item.get("data", {})  # Access the 'data' field
        if item_data.get("itemType") == "note":  # Only process notes
            parent_item_key = item_data.get("parentItem")
            parent_info = get_parent_info(parent_item_key, item_mapping)
            if parent_info:
                parent_item_title, parent_item_authors = parent_info
                note_content = item_data.get("note", "")
                # Remove HTML tags and decode any HTML entities (e.g., &amp;, &lt;)
                plain_text_note = re.sub(
                    r"<[^>]*>", "", note_content
                )  # Remove HTML tags
                plain_text_note = unescape(plain_text_note)  # Decode HTML entities
                note = {
                    "key": item_data.get("key"),
                    "parentItem": {
                        "key": parent_item_key,
                        "title": parent_item_title,
                        "authors": parent_item_authors,
                    },
                    "note": plain_text_note,
                }
                notes.append(note)
    print("Finished extracting notes")
    return notes


def load_from_json(filename):
    """Function to load existing data from a JSON file, or return an empty list if the file doesn't exist"""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return []


def save_to_json(items, filename="items.json"):
    """Function to save items to a JSON file, appending items with unique keys"""
    existing_items = load_from_json(filename)

    # Create a set of existing item keys to avoid duplicates
    existing_keys = {item["key"] for item in existing_items}

    # Filter out items that already exist in the JSON file based on their key
    new_items = [item for item in items if item["key"] not in existing_keys]

    if new_items:
        # Append the new items to the existing ones
        existing_items.extend(new_items)

        # Create the directory if it doesn't exist
        dirname = os.path.dirname(filename)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # Save the updated list back to the JSON file
        with open(filename, "w") as f:
            json.dump(existing_items, f, indent=4, ensure_ascii=False)
        print(f"Items saved to {filename}")
    else:
        print("No new items to add. All items already exist.")


def annotations_exporter():
    print("Starting the Zotero Annotations Exporter")

    api_vars = load_env_file()
    lib_type = api_vars["ZOTERO_LIBRARY_TYPE"]
    lib_id = api_vars["ZOTERO_LIBRARY_ID"]
    base_url = f"https://api.zotero.org/{lib_type}s/{lib_id}/items"

    if is_env_file_invalid():
        print("The .env has invalid parameters. Adjust it or delete it to start again.")
        return 1

    api_key = api_vars["ZOTERO_API_KEY"]
    items = fetch_items(base_url, api_key)
    if items:
        item_mapping = create_item_mapping(items)

        annotations = extract_annotations(items, item_mapping)
        save_to_json(annotations, "data/annotations.json")

        notes = extract_notes(items, item_mapping)
        save_to_json(notes, "data/notes.json")
    else:
        print("No items fetched. Exiting...")

    print("Finished running the Zotero Annotations Exporter")
    return 0


if __name__ == "__main__":
    annotations_exporter()
