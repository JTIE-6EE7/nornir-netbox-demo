"""
nornir-netbox-demo.py

This script uses Netbox as a Source of Truth for Nornir to automate provisioning, deployment and validation of a demo WAN.

Devices must be prepopulated in Netbox with a Primary IP address for management and be accessible via SSH.

JSON provisioning data must be populated in NetBox for each device in the Config Context field.

Script overview:

* Initialize Nornir/Netbox

* Enable SCP

* Get config variables from Netbox

* Render config files

* Apply Layer 3 configs

* Validate Layer 3 connectivity

* Apply BGP configs

* Validate BGP adjacencies

* Update Netbox data

* Disable SCP / save configs

Sample Config Context provisioning data for Netbox:

{
    "bgp": {
        "asn": 65511,
        "neighbors": [
            {
                "ipaddr": "172.20.12.2",
                "remote_asn": 65512
            },
            {
                "ipaddr": "172.20.13.3",
                "remote_asn": 65513
            }
        ],
        "networks": [
            {
                "net": "1.1.1.1",
                "mask": "255.255.255.255"
            },
            {
                "net": "172.20.12.0",
                "mask": "255.255.255.0"
            },
            {
                "net": "172.20.13.0",
                "mask": "255.255.255.0"
            }
        ],
        "rid": "1.1.1.1"
    },
    "interfaces": {
        "GigabitEthernet1": {
            "description": "Uplink to CSR-2",
            "ipaddr": "172.20.12.1 255.255.255.0",
            "state": "up"
        },
        "GigabitEthernet2": {
            "description": "Uplink to CSR-3",
            "ipaddr": "172.20.13.1 255.255.255.0",
            "state": "up"
        },
        "Loopback0": {
            "description": "Router ID",
            "ipaddr": "1.1.1.1 255.255.255.255",
            "state": "up"
        }
    }
}
"""


import re
import time
from netbox import NetBox
from nornir import InitNornir
from ipaddress import ip_interface
from nornir.plugins.tasks.networking import netmiko_send_config
from nornir.plugins.tasks.networking import netmiko_save_config
from nornir.plugins.tasks.networking import napalm_configure
from nornir.plugins.tasks.networking import napalm_ping
from nornir.plugins.tasks.networking import napalm_get
from nornir.plugins.tasks import text
from pprint import pprint


# print formatting function
def c_print(printme):
    """
    Function to print centered text with newline before and after
    """
    print(f"\n{printme.center(80, ' ')}\n")


# continue banner
def proceed():
    """
    Function to prompt to proceed or exit script
    """
    c_print("********** PROCEED? **********")
    # capture user input
    confirm = input(" " * 36 + "(y/n) ")
    # quit script if not confirmed
    if confirm.lower() != "y":
        c_print("******* EXITING SCRIPT *******")
        print("~" * 80)
        exit()
    else:
        c_print("********* PROCEEDING *********")


# Initialize The Norn and Netbox API
def kickoff():
    """
    This function initializes and returns the Nornir and Netbox objects.

    The config.yaml file holds the variables for the Netbox URL, Netbox API
    token and Nornir default username and password. It also disables the
    API SSL check.

    """
    # init The Norn from config file
    nr = InitNornir(config_file="./config.yaml")

    # pull vars from Nornir config file
    nb_url = nr.config.inventory.options["nb_url"]
    nb_token = nr.config.inventory.options["nb_token"]
    nr.inventory.defaults.username = nr.config.inventory.options["username"]
    nr.inventory.defaults.password = nr.config.inventory.options["password"]

    # set NAPALM platform
    nr.inventory.defaults.platform = "ios"

    # extract Netbox hostname from URL
    nb_host = re.sub("^.*//|:.*$", "", nb_url)

    # set filter on Netbox role
    nr = nr.filter(role="wan-router-provision")

    # print error and exit if no hosts found
    if len(nr.inventory.hosts) == 0:
        c_print("*** No matching hosts found in inventory ***")
        print("~" * 80)
        exit()

    # print banner if inventory populated
    else:
        c_print("This script will provision Cisco CSR1000v WAN routers")
        # print hosts included in inventory
        c_print("Inventory includes the following devices:")
        for host in nr.inventory.hosts.keys():
            c_print(f"*** {host} ***")

    # init Netbox API connection
    netbox = NetBox(
        host=nb_host,
        port=8000,
        use_ssl=False,
        auth_token=nb_token
    )

    # return initialized Norn and Netbox
    return nr, netbox


# enable SCP
def scp_enable(task):
    """
    Nornir task to enable SCP as required for for NAPALM
    """
    cmd = "ip scp server enable"
    task.run(task=netmiko_send_config, config_commands=cmd)
    c_print(f"*** {task.host}: SCP has been enabled ***")


# disable SCP and save configs
def scp_disable(task):
    """
    Nornir task to disable SCP after running NAPALM tasks
    """
    cmd = "no ip scp server enable"
    task.run(task=netmiko_send_config, config_commands=cmd)
    task.run(task=netmiko_save_config)
    c_print(f"*** {task.host}: SCP has been disabled ***")


# get config vars for each host
def get_config_vars(task, netbox):
    """
    Connect to Netbox, retrieve router configuration variables and save them
    to each device's task.host in Nornir. 
    """
    # get device ID for each device and save to task.host
    device_id = netbox.dcim.get_devices(name=task.host)[0]["id"]
    task.host["device_id"] = device_id

    # get config variables for each device and save to task.host
    nb_device = netbox.dcim.get_devices(id=device_id)
    task.host["config_vars"] = nb_device[0]["local_context_data"]


# render interface configurations
def interface_jinja(task):
    """
    Nornir task to render interface configurations
    """
    intf_cfg = task.run(
        task=text.template_file,
        template="interfaces.j2",
        path="templates/",
        **task.host,
    )
    # return configuration
    return intf_cfg.result


# render BGP routing configuration
def bgp_jinja(task):
    """
    Nornir task to render interface configurations
    """
    bgp_cfg = task.run(
        task=text.template_file,
        template="bgp.j2",
        path="templates/",
        **task.host,
    )
    # return configuration
    return bgp_cfg.result


# render router configs
def render_configs(task):
    """
    Nornir task to render router configurations
    """
    # render interface configs
    intf_cfg = interface_jinja(task)
    # function to run interface configs
    with open(f"configs/{task.host}_intf.txt", "w+") as file:
        file.write(intf_cfg)
    # print completed hosts
    c_print(f"*** {task.host}: inteface configuration rendered ***")

    # render BGP configs
    bgp_cfg = bgp_jinja(task)
    # function to write BGP configs
    with open(f"configs/{task.host}_bgp.txt", "w+") as file:
        file.write(bgp_cfg)
    # print completed hosts
    c_print(f"*** {task.host}: BGP routing configuration rendered ***")


# apply L3 router configs
def apply_l3_configs(task):
    """
    Nornir task to apply Layer 3 configurations to devices
    """
    # apply interface config file for each host
    task.run(task=napalm_configure, filename=f"configs/{task.host}_intf.txt")
    # print completed hosts
    c_print(f"*** {task.host}: Interface configuration applied ***")


# validate Layer 3 connectivity
def validate_l3(task):

    # init failed ping count
    failed_pings = 0
    # iterate over BGP neighbors
    for neighbor in task.host["config_vars"]["bgp"]["neighbors"]:
        # extract neighbor IP address to be pinged
        destination = neighbor["ipaddr"]

        # iterate over newly configured interfaces
        for intf in task.host["config_vars"]["interfaces"].values():
            # split ip address into address and mask
            source, mask = intf["ipaddr"].split(" ")
            # format source address for ip_interface usage
            src = ip_interface(f"{source}/{mask}")
            # format destination address for ip_interface usage
            dst = ip_interface(f"{destination}/{mask}")
            # compare souce and destination networks
            if src.network == dst.network:
                # if addresses are on the same network, ping
                ping = task.run(
                    task=napalm_ping,
                    dest=destination,
                    source=source
                )
                # check for ping errors
                if "success" in ping.result.keys():
                    # if ping is successful report nothing
                    if ping.result["success"]["packet_loss"] < 2:
                        pass

                    else:
                        # if ping has more than 1 packet lost report failure and increment counter
                        c_print(
                            f"*** {task.host} ping {source} > {destination} has FAILED *** "
                        )
                        failed_pings += 1

                else:
                    c_print(
                        f"*** {task.host} ping {source} > {destination} has FAILED *** "
                    )
                    failed_pings += 1

    # if no pings failed report success
    if failed_pings == 0:
        c_print(f"*** {task.host}: All ping tests have succeeded ***")


# apply BGP routing configs
def apply_bgp_configs(task):
    """
    Nornir task to apply Layer 3 configurations to devices
    """
    # apply BGP routing config file for each host
    task.run(task=napalm_configure, filename=f"configs/{task.host}_bgp.txt")
    # print completed hosts
    c_print(f"*** {task.host}: BGP routing configuration applied ***")


# validate BGP adjacencies
def validate_bgp(task):
    """
    Nornir task to validate BGP peers have come up
    """
    # get bgp status from devices
    bgp = task.run(
        task=napalm_get,
        getters=['get_bgp_neighbors']
    )
    # parse results for peer status
    for peer in bgp.result["get_bgp_neighbors"]["global"]["peers"].items():
        # set variable for peer status
        bgp_status = peer[1]["is_up"]
        # print message for peer up/down
        if bgp_status == True:
            c_print(f"*** {task.host}: BGP peer {peer[0]} is UP ***")
        if bgp_status == False:
            c_print(f"*** {task.host}: BGP peer {peer[0]} is DOWN ***")


# get updated info from each host
def get_updated_info(task, netbox):
    """
    Connect to Netbox, retrieve router interfaces and save them to each
    device's task.host in Nornir. Connect to each device with NAPALM
    and get interface information, serial number and software details.
    """
    # get interfaces for each device and save to task.host
    nb_intf = netbox.dcim.get_interfaces(device_id=task.host["device_id"])
    task.host["nb_interfaces"] = nb_intf

    # get interface information from devices and save to task.host
    intf = task.run(task=napalm_get, getters=["interfaces"])
    task.host["interfaces"] = intf.result["interfaces"]

    # get device information from devices and save to task.host
    intf = task.run(task=napalm_get, getters=["facts"])
    task.host["device_info"] = intf.result


# check if physical interface exists in Netbox
def is_interface_present(nb_interfaces, device_name, interface_name):
    for i in nb_interfaces:
        if i["name"] == interface_name and i["device"]["display_name"] == device_name:
            return True
    return False


# update Netbox with data from devices
def update_netbox(task, netbox):
    """
    Update Netbox with the information from the devices and config_vars
    """
    # get post configuration data from devices
    get_updated_info(task, netbox)
    # assign variable with physical interface data
    interfaces = task.host["interfaces"]
    # assign variable with Netbox interface data
    nb_interfaces = task.host["nb_interfaces"]
    # assign variable with device ID
    device_id = task.host["device_id"]

    for interface_name in interfaces.keys():
        # assign variable with interface description
        description = interfaces[interface_name]["description"]
        # assign variable with interface MAC address
        mac_address = interfaces[interface_name]["mac_address"]
        # assign E's for MAC address if it doesn't exist
        if mac_address == "None" or mac_address == "Unspecified" or mac_address == "":
            mac_address = "EE:EE:EE:EE:EE:EE"
        # create interface if it doesn't exist in Netbox
        if not is_interface_present(nb_interfaces, f"{task.host}", interface_name):

            c_print(f"*** {task.host}: creating Netbox interface: {interface_name} ***")
            netbox.dcim.create_interface(
                name=f"{interface_name}",
                device_id=device_id,
                interface_type=1000,
                description=description,
                mac_address=mac_address,
            )
        else:
            # update existing interfaces in Netbox
            c_print(f"*** {task.host}: updating Netbox Interface: {interface_name} ***")
            netbox.dcim.update_interface(
                device=f"{task.host}",
                interface=interface_name,
                description=description,
                mac_address=mac_address,
            )

    # get updated post configuration data from devices
    get_updated_info(task, netbox)
    # reassign variable with Netbox interface data
    nb_interfaces = task.host["nb_interfaces"]

    # iterate over interfaces from config_vars
    for intf in task.host["config_vars"]["interfaces"].items():
        # split ip and mask
        ip, mask = intf[1]["ipaddr"].split(" ")
        # create string of ipaddress object in CIDR notation
        ipaddr = str(ip_interface(f"{ip}/{mask}"))
        # check if IP exists in Netbox
        ip_exists = netbox.ipam.get_ip_addresses(address=ipaddr)
        # iterate over interfaces in Netbox
        for nb_intf in nb_interfaces:
            # compare interface in config_vars and Netbox
            if intf[0] == nb_intf["name"]:
                # if IP doesn't exist create it
                if ip_exists == []:
                    netbox.ipam.create_ip_address(
                        address=ipaddr, interface=nb_intf["id"]
                    )
                # if IP exists print error
                else:
                    c_print(
                        f"*** {task.host}: {ipaddr} exists - verify manually in Netbox ***"
                    )

    netbox.dcim.update_device(
        device_name=f"{task.host}",
        device_type={"id": 2},
        device_role={"id": 2},
        site={"id": 1}
    )

    c_print(
        f"*** {task.host}: moved from Provisioning to Production ***"
    )


# main function
def main():
    """
    Main function and script logic
    """

    # Initialize The Norn and Netbox
    nr, netbox = kickoff()
    proceed()
    print("~" * 80)

    # run The Norn to enable SCP
    c_print("Enabling SCP for NAPALM on all devices")
    nr.run(task=scp_enable)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn and Netbox to get configuration variables
    c_print("Gathering device configuration variables from Netbox")
    nr.run(task=get_config_vars, netbox=netbox)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to render configs
    c_print("Rendering device configurations")
    nr.run(task=render_configs)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to apply Layer 3 config files with proceed prompt
    c_print("Applying Layer 3 configuration files to all devices")
    proceed()
    nr.run(task=apply_l3_configs)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to validate Layer 3 connectivity
    c_print("Validating Layer 3 connectivity")
    time.sleep(20)
    nr.run(task=validate_l3)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to apply BGP configs with proceed prompt
    c_print("Applying BGP routing configuration files to all devices")
    proceed()
    nr.run(task=apply_bgp_configs)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to validate BGP adjacencies
    c_print("Validating BGP adjacencies")
    time.sleep(20)
    nr.run(task=validate_bgp)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn and Netbox to update information
    c_print("Updating Netbox with information from devices")
    nr.run(task=update_netbox, netbox=netbox)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)

    # run The Norn to disable SCP and save configs
    c_print("Disabling SCP server on all devices")
    nr.run(task=scp_disable)
    c_print(f"Failed hosts: {nr.data.failed_hosts}")
    print("~" * 80)


if __name__ == "__main__":
    main()
