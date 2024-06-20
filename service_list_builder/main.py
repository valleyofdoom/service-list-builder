import argparse
import ctypes
import logging
import os
import re
import sys
import winreg
from collections import deque
from configparser import ConfigParser, SectionProxy
from datetime import datetime
from typing import Any

import pywintypes
import win32api
import win32service
import win32serviceutil
from consts import HIVE, LOAD_HIVE_LINES, USER_MODE_TYPES, VERSION

LOG_CLI = logging.getLogger("CLI")


def read_value(path: str, value_name: str) -> Any | None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            path,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            return winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return None


def get_dependencies(service: str, kernel_mode: bool) -> set[str]:
    dependencies: list[str] | None = read_value(
        f"{HIVE}\\Services\\{service}",
        "DependOnService",
    )

    # base case
    if dependencies is None or len(dependencies) == 0:
        return set()

    if not kernel_mode:
        # remove kernel-mode services from dependencies list so we are left with
        # user-mode dependencies only
        dependencies = [
            dependency
            for dependency in dependencies
            if read_value(f"{HIVE}\\Services\\{dependency}", "Type") in USER_MODE_TYPES
        ]

    child_dependencies = {
        child_dependency
        for dependency in dependencies
        for child_dependency in get_dependencies(dependency, kernel_mode)
    }

    return set(dependencies).union(child_dependencies)


def get_present_services() -> dict[str, str]:
    # keeps track of service in lowercase (key) and actual service name (value)
    present_services: dict[str, str] = {}

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{HIVE}\\Services") as key:
        num_subkeys = winreg.QueryInfoKey(key)[0]

        for i in range(num_subkeys):
            service_name = winreg.EnumKey(key, i)

            # handle (remove) user ID in service name
            if "_" in service_name:
                LOG_CLI.debug('removing "_" in "%s"', service_name)
                service_name = service_name.rpartition("_")[0]

            present_services[service_name.lower()] = service_name

    return present_services


def parse_config_list(
    service_list: SectionProxy,
    present_services: dict[str, str],
) -> set[str]:
    return {
        present_services[lower_service]
        for service in service_list
        if (lower_service := service.lower()) in present_services
    }


def get_file_metadata(file_path: str, attribute: str) -> str:
    lang, code_page = win32api.GetFileVersionInfo(file_path, "\\VarFileInfo\\Translation")[0]

    file_info_key = f"\\StringFileInfo\\{lang:04x}{code_page:04x}\\"
    product_name = win32api.GetFileVersionInfo(file_path, f"{file_info_key}{attribute}")

    if not product_name:
        return ""

    return str(product_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--config",
        metavar="<config>",
        type=str,
        help="path to lists config file",
    )
    group.add_argument(
        "--get-dependencies",
        metavar="<service>",
        type=str,
        help="returns the entire dependency tree for a given service",
    )

    parser.add_argument(
        "--disable-running",
        help="only disable services specified in the list that are currently running",
        action="store_true",
    )
    parser.add_argument(
        "--kernel-mode",
        help="includes kernel-mode services in the dependency tree when using --get-dependencies",
        action="store_true",
    )
    parser.add_argument(
        "--disable-service-warning",
        help="disable the non-Windows services warning",
        action="store_true",
    )
    args = parser.parse_args()

    if args.kernel_mode and not args.get_dependencies:
        parser.error("--kernel-mode can only be used with --get_dependencies")

    if args.disable_running and not args.config:
        parser.error("--disable-running can only be used with --config")

    return args


def main() -> int:
    logging.basicConfig(format="[%(name)s] %(levelname)s: %(message)s", level=logging.INFO)

    present_services = get_present_services()

    print(
        f"service-list-builder Version {VERSION} - GPLv3\n",
    )

    if not ctypes.windll.shell32.IsUserAnAdmin():
        LOG_CLI.error("administrator privileges required")
        return 1

    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))
    elif __file__:
        os.chdir(os.path.dirname(__file__))

    args = parse_args()

    if args.get_dependencies:
        lower_get_dependencies = args.get_dependencies.lower()
        if lower_get_dependencies not in present_services:
            LOG_CLI.error("%s not exists as a service", args.get_dependencies)
            return 1

        dependencies = {
            present_services[dependency.lower()]
            for dependency in get_dependencies(args.get_dependencies, args.kernel_mode)
        }
        service_name = present_services[lower_get_dependencies]

        print(
            (
                f"{service_name} has 0 dependencies"
                if len(dependencies) == 0
                else f"{service_name} depends on {', '.join(dependencies)}"
            ),
        )
        return 0

    if not os.path.exists(args.config):
        LOG_CLI.error("config file %s not found", args.config)
        return 1

    config = ConfigParser(
        allow_no_value=True,
        delimiters=("="),
        inline_comment_prefixes="#",
    )
    # prevent lists imported as lowercase
    config.optionxform = lambda optionstr: optionstr
    config.read(args.config)

    service_dump: set[str] = set()

    # load sections from config and handle case insensitive entries
    enabled_services = parse_config_list(config["enabled_services"], present_services)
    individual_disabled_services = parse_config_list(
        config["individual_disabled_services"],
        present_services,
    )
    rename_binaries = {binary for binary in config["rename_binaries"] if binary != ""}

    # check dependencies
    has_dependency_errors = False

    # required for lowercase comparison
    lower_services_set: set[str] = {service.lower() for service in enabled_services}

    for service in enabled_services.union(individual_disabled_services):
        # get a set of the dependencies in lowercase
        dependencies = {service.lower() for service in get_dependencies(service, kernel_mode=False)}

        # check which dependencies are not in the user's list
        # then get the actual name from present_services as it was converted to lowercase to handle case inconsistency in Windows
        missing_dependencies = {
            present_services[dependency] for dependency in dependencies.difference(lower_services_set)
        }

        if len(missing_dependencies) > 0:
            has_dependency_errors = True
            LOG_CLI.error("%s depends on %s", service, ", ".join(missing_dependencies))

    if has_dependency_errors:
        return 1

    if enabled_services:
        # populate service_dump with all user mode services that are not in enabled_services section
        for lower_service_name, service_name in present_services.items():
            # don't add services that the user want's to keep enabled in the service dump
            if lower_service_name in lower_services_set:
                continue

            service_type = read_value(f"{HIVE}\\Services\\{service_name}", "Type")

            if service_type is not None:
                service_type = int(service_type)

                if service_type in USER_MODE_TYPES:
                    service_dump.add(service_name)

    if not args.disable_service_warning:
        # check if any services are non-Windows services as the user
        # likely does not want to disable these
        non_microsoft_service_count = 0
        unknown_company_service_count = 0

        # use lowercase key as the path will be converted to lowercase when comparing
        replacements = {
            "\\systemroot\\": "C:\\Windows\\",
            "system32\\": "C:\\Windows\\System32\\",
            "\\??\\": "",
        }

        for service_name in service_dump.union(individual_disabled_services):
            image_path = read_value(f"{HIVE}\\Services\\{service_name}", "ImagePath")

            if image_path is None:
                continue

            path_match = re.match(r".*?\.(exe|sys)\b", image_path, re.IGNORECASE)

            if path_match is None:
                LOG_CLI.error("path match failed for %s", image_path)
                unknown_company_service_count += 1
                continue

            # expand vars
            binary_path: str = os.path.expandvars(path_match[0])
            lower_binary_path = binary_path.lower()

            # resolve paths
            if lower_binary_path.startswith('"'):
                lower_binary_path = lower_binary_path[1:]

            for starts_with, replacement in replacements.items():
                if lower_binary_path.startswith(starts_with):
                    lower_binary_path = lower_binary_path.replace(starts_with, replacement)

            if not os.path.exists(lower_binary_path):
                print(f"unable to get binary path for {service_name}")
                unknown_company_service_count += 1
                continue

            try:
                company_name = get_file_metadata(lower_binary_path, "CompanyName")

                if not company_name:
                    raise pywintypes.error

                if company_name != "Microsoft Corporation":
                    print(f'"{service_name}" is not a Windows service')
                    non_microsoft_service_count += 1
            except pywintypes.error:
                print(f"unable to get CompanyName for {service_name}")
                unknown_company_service_count += 1

        if non_microsoft_service_count + unknown_company_service_count != 0:
            print(
                f"\n{non_microsoft_service_count} non-Windows services detected, {unknown_company_service_count} service vendors are unknown. are you sure you want to disable these?\nedit the config or use --disable-service-warning to suppress this warning if this is intentional"
            )
            return 1

    if args.disable_running:
        for service in service_dump.copy():
            if not win32serviceutil.QueryServiceStatus(service)[1] == win32service.SERVICE_RUNNING:
                service_dump.remove(service)

    # store contents of batch scripts
    ds_lines: deque[str] = deque()
    es_lines: deque[str] = deque()

    for binary in rename_binaries:
        if os.path.exists(f"C:{binary}"):
            file_name = os.path.basename(binary)
            file_extension = os.path.splitext(file_name)[1]

            if file_extension == ".exe":
                # processes should be killed before being renamed
                ds_lines.append(f"taskkill /f /im {file_name}")

            last_index = binary[-1]  # .exe gets renamed to .exee
            ds_lines.append(f'REN "%DRIVE_LETTER%:{binary}" "{file_name}{last_index}"')
            es_lines.append(f'REN "%DRIVE_LETTER%:{binary}{last_index}" "{file_name}"')
        else:
            LOG_CLI.info("item does not exist: %s... skipping", binary)

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{HIVE}\\Control\\Class") as key:
        num_subkeys = winreg.QueryInfoKey(key)[0]

        for i in range(num_subkeys):
            filter_id = winreg.EnumKey(key, i)

            for filter_type in ("LowerFilters", "UpperFilters"):
                original: list[str] | None = read_value(
                    f"{HIVE}\\Control\\Class\\{filter_id}",
                    filter_type,
                )

                # check if the filter exists
                if original is not None:
                    new = original.copy()  # to keep a backup of the original
                    for driver in original:
                        if driver in service_dump:
                            new.remove(driver)

                    # check if original was modified at all
                    if original != new:
                        ds_lines.append(
                            f'reg.exe add "HKLM\\%HIVE%\\Control\\Class\\{filter_id}" /v "{filter_type}" /t REG_MULTI_SZ /d "{"\\0".join(new)}" /f',
                        )
                        es_lines.append(
                            f'reg.exe add "HKLM\\%HIVE%\\Control\\Class\\{filter_id}" /v "{filter_type}" /t REG_MULTI_SZ /d "{"\\0".join(original)}" /f',
                        )

    for service in sorted(service_dump, key=str.lower):
        original_start_value = read_value(f"{HIVE}\\Services\\{service}", "Start")

        if original_start_value is not None:
            ds_lines.append(
                f'reg.exe add "HKLM\\%HIVE%\\Services\\{service}" /v "Start" /t REG_DWORD /d "4" /f',
            )

            es_lines.append(
                f'reg.exe add "HKLM\\%HIVE%\\Services\\{service}" /v "Start" /t REG_DWORD /d "{original_start_value}" /f',
            )

    if not ds_lines:
        LOG_CLI.info("there are no changes to write to the scripts")
        return 0

    for script_lines in (ds_lines, es_lines):
        for line in LOAD_HIVE_LINES.split("\n")[::-1]:
            script_lines.appendleft(line)

        script_lines.append("shutdown /r /f /t 0")

    current_time = datetime.now()

    if not os.path.exists("build"):
        os.mkdir("build")

    build_dir = os.path.join("build", f"build-{current_time.strftime("%d%m%y%H%M%S")}")

    os.makedirs(build_dir)

    with open(os.path.join(build_dir, "Services-Disable.bat"), "w", encoding="utf-8") as file:
        for line in ds_lines:
            file.write(f"{line}\n")

    with open(os.path.join(build_dir, "Services-Enable.bat"), "w", encoding="utf-8") as file:
        for line in es_lines:
            file.write(f"{line}\n")

    LOG_CLI.info("done - scripts built in .\\%s", build_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
