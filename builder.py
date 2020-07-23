import plistlib
import shutil
import subprocess
from os import chdir
from pathlib import Path


class Builder():
    def __init__(self):
        self.lilu = {}
        self.script_dir = Path(__file__).parent.absolute()

        self.working_dir = self.script_dir / Path("Temp")
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir)
        self.working_dir.mkdir()

        self.build_dir = self.script_dir / Path("Builds")
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        self.build_dir.mkdir()

    @staticmethod
    def _debug(string: str):
        return string.replace("Release 10.6", "Debug").replace("Release", "Debug") \
            .replace("release", "debug").replace("RELEASE", "DEBUG")

    @staticmethod
    def _expand_globs(path: str):
        if "*" in path:
            path = Path(path)
            parts = path.parts[1:] if path.is_absolute() else path.parts
            return list(Path(path.root).glob(str(Path("").joinpath(*parts))))
        else:
            return [Path(path)]

    def _build_lilu(self):
        chdir(self.working_dir)
        if not self.lilu:
            print("Building prerequiste: Lilu...")
            if Path("Lilu").exists():
                shutil.rmtree(Path("Lilu"))
            print("\tCloning the repo...")
            result = subprocess.run("git clone https://github.com/acidanthera/Lilu.git".split(), capture_output=True)
            if result.returncode != 0:
                print("\tClone failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
            chdir(self.working_dir / Path("Lilu"))
            print("\tBuilding debug version...")
            result = subprocess.run("xcodebuild -quiet -configuration Debug".split(), capture_output=True)
            if result.returncode != 0:
                print("\tBuild failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
            result = subprocess.run("git rev-parse HEAD".split(), capture_output=True)
            if result.returncode != 0:
                print("\tObtaining commit hash failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
            else:
                commithash = result.stdout.decode().strip()
            shutil.copytree(Path("build/Debug/Lilu.kext"), self.working_dir / Path("Lilu.kext"))
            self.lilu = [commithash, self.working_dir / Path("Lilu.kext")]
        return self.lilu[1]

    def build(self, plugin, commithash=None):
        name = plugin["Name"]
        url = plugin["URL"]
        needs_lilu = plugin.get("Lilu", False)
        command = plugin.get("Command")
        prebuild = plugin.get("Pre-Build", [])
        postbuild = plugin.get("Post-Build", [])
        build_opts = plugin.get("Build Opts", [])
        build_dir = plugin.get("Build Dir", "./build/Release")
        p_info = plugin.get("Info", name + ".kext/Contents/Info.plist")
        debug = plugin.get("Debug", False)
        b_type = plugin.get("Type", "Kext")
        d_file = plugin.get("Debug File", "build/Debug/*.kext")
        r_file = plugin.get("Release File", "build/Release/*.kext")
        extra_files = plugin.get("Extras", None)
        v_cmd = plugin.get("Version", None)

        if debug:
            # we need to prep some stuff for debug builds
            for task in prebuild:
                task["args"] = [self._debug(x) for x in task["args"]]
            for task in postbuild:
                task["args"] = [self._debug(x) for x in task["args"]]
            build_opts = [self._debug(x) for x in build_opts]
            build_dir = self._debug(build_dir)

        chdir(self.working_dir)

        if needs_lilu:
            self._build_lilu()

        chdir(self.working_dir)
        print("Building " + name + "...")
        if Path(name).exists():
            shutil.rmtree(Path(name))
        print("\tCloning the repo...")
        result = subprocess.run(["git", "clone", url + ".git"], capture_output=True)
        if result.returncode != 0:
            print("\tClone failed!")
            print(result.stdout.decode())
            print(result.stderr.decode())
            return False
        chdir(self.working_dir / Path(name))

        if commithash:
            print("\tChecking out to " + commithash + "...")
            result = subprocess.run(["git", "checkout", commithash], capture_output=True)
            if result.returncode != 0:
                print("\tCheckout failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
        else:
            result = subprocess.run("git rev-parse HEAD".split(), capture_output=True)
            if result.returncode != 0:
                print("\tObtaining commit hash failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
        chdir(self.working_dir / Path(name))
        if needs_lilu:
            shutil.copytree(self._build_lilu(), self.working_dir / Path(name) / Path("Lilu.kext"))
        chdir(self.working_dir / Path(name))
        if prebuild:
            print("\tRunning prebuild tasks...")
            for task in prebuild:
                print("\t\tRunning task '" + task["name"] + "'")
                args = [task["path"]]
                args.extend(task["args"])
                result = subprocess.run(args, capture_output=True)
                if result.returncode != 0:
                    print("\t\tTask failed!")
                    print(result.stdout.decode())
                    print(result.stderr.decode())
                    return False
                else:
                    print("\t\tTask completed.")
        chdir(self.working_dir / Path(name))
        if command:
            print("\tBuilding...")
            if isinstance(command, str):
                command = command.split()
            result = subprocess.run(command, capture_output=True)
            if result.returncode != 0:
                print("\tBuild failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                print("\tReturn code: " + str(result.returncode))
                return False
        else:
            print("\tBuilding release version...")
            args = "xcodebuild -quiet -configuration Release".split()
            args.extend(build_opts)
            args.append("BUILD_DIR=build/")
            result = subprocess.run(args, capture_output=True)
            if result.returncode != 0:
                print("\tBuild failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                print("\tReturn code: " + str(result.returncode))
                return False
            print("\tBuilding debug version...")
            args = "xcodebuild -quiet -configuration Debug".split()
            args.extend(build_opts)
            args.append("BUILD_DIR=build/")
            result = subprocess.run(args, capture_output=True)
            if result.returncode != 0:
                print("\tBuild failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                print("\tReturn code: " + str(result.returncode))
                return False
        chdir(self.working_dir / Path(name))
        if postbuild:
            print("\tRunning postbuild tasks...")
            for task in postbuild:
                print("\t\tRunning task '" + task["name"] + "'")
                args = [task["path"]]
                args.extend(task["args"])
                result = subprocess.run(args, capture_output=True)
                if result.returncode != 0:
                    print("\t\tTask failed!")
                    print(result.stdout.decode())
                    print(result.stderr.decode())
                    return False
                else:
                    print("\t\tTask completed.")
        chdir(self.working_dir / Path(name))
        if v_cmd:
            if isinstance(v_cmd, str):
                v_cmd = v_cmd.split()
            result = subprocess.run(v_cmd, capture_output=True)
            if result.returncode != 0:
                print("\tRunning version command failed!")
                print(result.stdout.decode())
                print(result.stderr.decode())
                return False
            else:
                version = result.stdout.decode().strip()
        elif b_type == "Kext":
            plistpath = Path(build_dir).joinpath(p_info)
            version = plistlib.load(plistpath.open(mode="rb"))["CFBundleVersion"]
        else:
            print("\tNo version command!")
            return False
        print("\tVersion: " + version)
        category_type = {"Kext": "Kexts", "Bootloader": "Bootloaders", "Other": "Others"}.get(b_type)
        print("\tCopying to build directory...")
        extras = []
        # (extras.extend(self._expand_globs(i)) for i in extra_files) if extra_files is not None else None  # pylint: disable=expression-not-assigned
        if extra_files is not None:
            for i in extra_files:
                extras.extend(self._expand_globs(i))
        debug_file = self._expand_globs(d_file)[0]
        release_file = self._expand_globs(r_file)[0]
        debug_dir = self.build_dir / Path(category_type) / Path(name) / Path(commithash) / Path("Debug")
        release_dir = self.build_dir / Path(category_type) / Path(name) / Path(commithash) / Path("Release")
        for directory in [debug_dir, release_dir]:
            if directory.exists():
                shutil.rmtree(directory)
            directory.mkdir(parents=True)
        if extras:
            for i in extras:
                if i.is_dir():
                    print(i + " is a dir; please fix!")
                    shutil.copytree(i, debug_dir / i.name)
                    shutil.copytree(i, release_dir / i.name)
                elif i.is_file():
                    shutil.copy(i, debug_dir)
                    shutil.copy(i, release_dir)
                else:
                    print(i + " is not a dir or a file!")
                    continue
        if debug_file.is_dir():
            print(debug_file + " is a dir; please fix!")
            shutil.copytree(debug_file, debug_dir / debug_file.name)
        elif debug_file.is_file():
            shutil.copy(debug_file, debug_dir)

        if release_file.is_dir():
            print(release_file + " is a dir; please fix!")
            shutil.copytree(release_file, release_dir / release_file.name)
        elif release_file.is_file():
            shutil.copy(release_file, release_dir)
        return {"debug": debug_dir / Path(debug_file.name), "release": release_dir / Path(release_file.name), "extras": [debug_dir / Path(i.name) for i in extras], "version": version}
