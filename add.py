import datetime
import hashlib
import json
import subprocess
import time
from pathlib import Path

import dateutil.parser
import magic
import purl
from hammock import Hammock as hammock

mime = magic.Magic(mime=True)


def hash_file(file_path: Path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def expand_globs(path: str):
    path = Path(path)
    parts = path.parts[1:] if path.is_absolute() else path.parts
    return list(Path(path.root).glob(str(Path("").joinpath(*parts))))


def upload_release_asset(release_id, token, file_path: Path):
    upload_url = hammock("https://api.github.com/repos/dhinakg/ktextrepo-beta/releases/" + str(release_id), auth=("dhinakg", token)).GET().json()
    upload_url = upload_url["upload_url"]
    mime_type = mime.from_file(str(file_path.resolve()))
    if not mime_type[0]:
        print("Failed to guess mime type!")
        return False

    asset_upload = hammock(str(purl.Template(upload_url).expand({"name": file_path.name, "label": file_path.name})), auth=("dhinakg", token)).POST(
        data=file_path.read_bytes(),
        headers={"content-type": mime_type}
    )
    return asset_upload.json()["browser_download_url"]


def paginate(url, token):
    url = hammock(url, auth=("dhinakg", token)).GET()
    if url.links == {}:
        return url.json()
    else:
        container = url.json()
        while url.links.get("next"):
            url = hammock(url.links["next"]["url"], auth=("dhinakg", token)).GET()
            container += url.json()
        return container


def add_built(plugin, token):
    plugin_info = plugin["plugin"]
    commit_info = plugin["commit"]
    files = plugin["result"]

    script_dir = Path(__file__).parent.absolute()
    config_path = script_dir / Path("Config/config.json")
    config_path.touch()
    config = json.load(config_path.open())

    name = plugin_info["Name"]
    plugin_type = plugin_info.get("Type", "Kext")

    ind = None

    if not config.get(name, None):
        config[name] = {}
    if not config[name].get("type", None):
        config[name]["type"] = plugin_type
    if not config[name].get("versions", None):
        config[name]["versions"] = []

    release = {}
    if config[name]["versions"]:
        config[name]["versions"] = [i for i in config[name]["versions"] if not config["commit"]["sha"] == commit_info["sha"]]

    release["commit"] = {"sha": commit_info["sha"], "message": commit_info["commit"]["message"]}
    release["version"] = files["version"]
    release["dateadded"] = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    release["datecommitted"] = dateutil.parser.parse(commit_info["commit"]["committer"]["date"]).isoformat()
    release["source"] = "built"

    releases_url = hammock("https://api.github.com/repos/dhinakg/ktextrepo-beta/releases", auth=("dhinakg", token))

    # Delete previous releases
    for i in paginate("https://api.github.com/repos/dhinakg/ktextrepo-beta/releases", token):
        if i["name"] == (name + " " + release["commit"]["sha"][:7]):
            print("\tDeleting previous release...")
            releases_url(i["id"]).DELETE()
            time.sleep(3)  # Prevent race conditions

    # Delete tags
    check_tag = hammock("https://api.github.com/repos/dhinakg/ktextrepo-beta/git/refs/tags/" + name + "-" + release["commit"]["sha"][:7], auth=("dhinakg", token))
    if check_tag.GET().status_code != 404:
        print("\tDeleting previous tag...")
        check_tag.DELETE()
        time.sleep(3)  # Prevent race conditions

    # Create release
    create_release = releases_url.POST(json={
        "tag_name": name + "-" + release["commit"]["sha"][:7],
        "target_commitish": "builds",
        "name": name + " " + release["commit"]["sha"][:7]
    })
    # print(create_release.json()["id"])
    release["release"] = {"id": create_release.json()["id"], "url": create_release.json()["html_url"]}

    if not release.get("hashes", None):
        release["hashes"] = {"debug": {"sha256": ""}, "release": {"sha256": ""}}

    release["hashes"]["debug"] = {"sha256": hash_file(files["debug"])}
    release["hashes"]["release"] = {"sha256": hash_file(files["release"])}

    if files["extras"]:
        for file in files["extras"]:
            release["hashes"][file.name] = {"sha256": hash_file(file)}

    if not release.get("links", None):
        release["links"] = {}

    for i in ["debug", "release"]:
        release["links"][i] = upload_release_asset(release["release"]["id"], token, files[i])

    if files["extras"]:
        if not release.get("extras", None):
            release["extras"] = {}
        for file in files["extras"]:
            release["extras"][file.name] = upload_release_asset(release["release"]["id"], token, file)
    new_line = "\n"  # No escapes in f-strings

    release["release"]["description"] = f"""{commit_info['commit']['message'].strip()}
[{commit_info['sha']}]({commit_info['html_url']}) ([browse tree]({commit_info['html_url'].replace("/commit/", "/tree/")}))

**Hashes**:

Debug:

{files["debug"].name + ': ' + release['hashes']['debug']["sha256"]}

Release:

{files["release"].name + ': ' + release['hashes']['release']["sha256"]}

{'Extras:' if files["extras"] else ''}

{new_line.join([file.name + ': ' + release['hashes'][file.name]['sha256'] for file in files["extras"]]) if files["extras"] else ''}
"""

    hammock("https://api.github.com/repos/dhinakg/ktextrepo-beta/releases/" + str(release["release"]["id"]), auth=("dhinakg", token)).POST(json={
        "body": release["release"]["description"]
    })

    config[name]["versions"].insert(0, release)
    json.dump(config, config_path.open(mode="w"), indent=2, sort_keys=True)

    result = subprocess.run(["git", "commit", "-am", "Deploying to builds"], capture_output=True, cwd=(script_dir / Path("Config")))
    if result.returncode != 0:
        print("Commit failed!")
        print(result.stdout.decode())
        print(result.stderr.decode())
        return
    result = subprocess.run("git push".split(), capture_output=True, cwd=(script_dir / Path("Config")))
    if result.returncode != 0:
        print("Push failed!")
        print(result.stdout.decode())
        print(result.stderr.decode())
        return
