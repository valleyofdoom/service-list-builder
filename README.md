# service-list-builder

[![Downloads](https://img.shields.io/github/downloads/valleyofdoom/service-list-builder/total.svg)](https://github.com/valleyofdoom/service-list-builder/releases)

I am not responsible for damage caused to computer. This tool is powerful and for advanced users only. There is a risk of damaging your operating system if you disable core services that are required for Windows to function correctly. It is your responsibility to use suitable service configurations for your specific operating system. If you would like to re-build the scripts, ensure to run the generated ``Services-Enable.bat`` script beforehand as the tool relies on the current state of services for building future scripts.

## Usage and Program Logic

- Download the latest release from the [releases tab](https://github.com/valleyofdoom/service-list-builder/releases)

- Open ``lists.ini`` in a text editor

  - Every user-mode service **NOT** specified in the ``[enabled_services]`` section will get disabled. This section acts as whitelist of user-mode services **NOT** to disable

  - Individual services to disable can be explicitly specified in the ``[individual_disabled_services]`` section. This section does not follow the *disable all except* logic. Only the services specified in this section will get disabled. This is useful in situations where the user only needs to disable a few user-mode services instead of using the *batch* approach with ``[enabled_services]`` or you would like to disable kernel-mode services at all

  - Paths to folders or binaries can be specified in the ``[rename_binaries]`` section. The logic behind this is that when a binary gets renamed to anything other than its original file name, it will not run. Exclude the drive letter from the path as it is handled by the script. For example, ``C:\folder\program.exe`` should be written as ``\folder\program.exe``

- Pass ``lists.ini`` as an argument to the program through the command-line with the command below to build the scripts

  ```bat
  service-list-builder --config lists.ini
  ```

- The scripts will be built in the ``build`` folder. [NSudo](https://github.com/M2Team/NSudo) is required to run the scripts with ``Enable All Privileges`` option enabled to prevent errors when writing to registry and renaming files. It is included in the release

<!-- ## Example

<img src="/assets/img/lists.png" width="1000"> -->

## Restoring Services Offline

> [!IMPORTANT]
> The methodology is only applicable to scripts built with service-list-builder v1.0.0 and above.

If you are unable to boot or something goes completely wrong after running ``Services-Disable.bat`` for whatever reason, you can simply restore them offline by loading the registry hive and running the ``Services-Enable.bat`` script. This requires an already installed dual-boot, Windows recovery environment or Windows setup.

1. Open the ``Services-Enable.bat`` script in a text editor and change the ``DRIVE_LETTER`` variable to the partition in which the problematic Windows installation is installed to (be careful not to use the wrong drive letter if multiple dual-boots are configured)

    - If you are in WinRE or Windows setup, you can use notepad's ``File -> Open...`` dialog by typing ``notepad`` in CMD to browse the file system

2. Run the script with NSudo

3. Now that the services should be restored, boot to the operating system. Don't forget to change the ``DRIVE_LETTER`` variable back to it's default value

## Debugging Services

Often while experimenting, some specific functionality might be broken after running the ``Services-Disable.bat`` script but works as intended after running the ``Services-Enable.bat`` script. If the functionality is still broken after enabling services, then the problem is not related to services.

As a short-term and temporary solution, you can simply run ``Services-Enable.bat``, do whatever you are trying to do, then run ``Services-Disable.bat`` again (that's the idea of having toggle scripts!). For a long-term solution, you need to find out what services are required for the functionality using the systematic methodology below. Once you have found which services are a dependency of the given functionality, you can update your ``lists.ini`` and/or ``Services-Disable.bat`` script.

### Methodology

> [!IMPORTANT]
> The methodology is only applicable to scripts built with service-list-builder v1.0.0 and above.

1. If you haven't disabled services at this stage, run the ``Services-Disable.bat`` script

2. Create a new script named ``Debug-Services.bat``

3. Create a text file named ``dependencies.txt``

4. Open the ``Services-Enable.bat`` and ``Debug-Services.bat`` scripts in a text editor

5. In the ``Services-Enable.bat`` script, copy all the lines from the start of the script until and including the ``reg query`` command into the ``Debug-Services.bat`` script. The lines that rename binaries (if you have any) must also be copied. These lines begin with ``REN``

6. If you have any lines that change the ``LowerFilters`` and/or ``UpperFilters`` registry keys, you will need to handle those first, otherwise, you can continue to step 7 if you don't have any. Copy those lines and the line that changes the ``Start`` value for each driver inside the filter to the ``Debug-Services.bat`` script. The null terminator character (``\0``) is not part of the driver name (e.g. ``\0iorate`` is ``iorate``).

    <details>

    <summary>Example</summary>

    - An example of what the filters part of the ``Services-Enable.bat`` script could look like:

        ```bat
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e967-e325-11ce-bfc1-08002be10318}" /v "LowerFilters" /t REG_MULTI_SZ /d "EhStorClass" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Control\Class\{71a27cdd-812a-11d0-bec7-08002be2092f}" /v "LowerFilters" /t REG_MULTI_SZ /d "fvevol\0iorate\0rdyboost" /f
        ...
        ```

    - The lines that must be copied to the ``Debug-Services.bat`` script:

        ```bat
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e967-e325-11ce-bfc1-08002be10318}" /v "LowerFilters" /t REG_MULTI_SZ /d "EhStorClass" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Control\Class\{71a27cdd-812a-11d0-bec7-08002be2092f}" /v "LowerFilters" /t REG_MULTI_SZ /d "fvevol\0iorate\0rdyboost" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\EhStorClass" /v "Start" /t REG_DWORD /d "0" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\fvevol" /v "Start" /t REG_DWORD /d "0" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\iorate" /v "Start" /t REG_DWORD /d "0" /f
        reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\rdyboost" /v "Start" /t REG_DWORD /d "0" /f
        ```

    </details>

7. Copy the lines that enable the next 10 services from the ``Services-Enable.bat`` script to the ``Debug-Services.bat`` script

8. Run the ``Debug-Services.bat`` script with NSudo and restart your PC

9. Test the functionality. If it is **NOT** working then return to step 7, otherwise, continue to step 10

10. Disable the last 10 services in the ``Debug-Services.bat`` individually by changing the start value to 4 then restart your PC. Keep repeating until the functionality breaks again. When it breaks, continue to step 11

11. Now that you have identified which service breaks the functionality, try to re-enable it. If you can reproduce the functionality breaking while the service is disabled and works with it enabled a few times, then make a note of this service in ``dependencies.txt`` and continue to the next step

12. Delete ``Debug-Services.bat`` as it is no longer required

13. The service's dependencies must also be enabled if there are any. [service-list-builder](https://github.com/valleyofdoom/service-list-builder) can be used to get the entire dependency tree for a given service with the command below. Note every dependency that appears in the output to ``dependencies.txt``

    ```bat
    service-list-builder.exe --kernel-mode --get-dependencies <service>
    ```

14. For each service that you noted down in ``dependencies.txt``, get the default start value for it from the ``Services-Enable.bat`` script and change the start value for the service in the ``Services-Disable.bat`` script. Run the ``Services-Disable.bat`` script with NSudo to check whether the functionality is working. If it is not working, return to step 1 and repeat the entire process with the newly edited/latest ``Services-Disable.bat`` script, otherwise, continue to step 15. This is because a service that is required for the functionality might not have any service dependencies

15. At this stage, your functionality should be working after running the ``Services-Disable.bat`` script. Now you can update your ``lists.ini`` with everything that you noted in ``dependencies.txt`` for the future
