# bisdn-switch-interface
Script to save switch interface configurations in BISDN Linux and other systemd-networkd distros.

I bought an Edgecore AS4610 switch for use at home that came with BISDN Linux. I quickly discovered that there is no real CLI other than the linux shell, and that using iproute2 and systemd-networkd configs to configure switch ports is about the most annoying method of doing this normally simple task. Coming from Cisco/Juniper world of a couple simple, straight forward commands to several config files per interface is not exactly what I had in mind.

Here is a script that will generate or update the configs for your run of the mill trunk and access ports. I won't promise that it works perfectly 100% of the time. I may add functionality in the future when and if I need it.
