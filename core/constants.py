"""Global constants shared across ArmFirewall modules."""

from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]



DB_DIR = ROOT_DIR / "db"
CONF_DIR = ROOT_DIR / "conf"
OCI_CONF_DIR = CONF_DIR / "oci"
OCI_PRIVATE_KEY_PATH = OCI_CONF_DIR / "oci_privatekey.pem"
OCI_CONFIG_PATH = OCI_CONF_DIR / "oci.config"
LOG_DIR = ROOT_DIR / "logs"
SUPERVISOR_CONF = CONF_DIR / "supervisord.conf"
IFACE_DB_PATH = DB_DIR / "iface.db"
SYSTEM_DB_PATH = DB_DIR / "system.db"
NETWORK_DB_PATH = DB_DIR / "network.db"
LOG_DB_PATH = DB_DIR / "logs.db"
USERS_DB_PATH = DB_DIR / "users.db"
WORK_REQUEST_DB_PATH = DB_DIR / "work-requests.db"
WORK_REQUESTS_DEFAULT_PAGE_SIZE = 50
WORK_REQUESTS_MAX_PAGE_SIZE = 100
IFACE_PROC_WORK_REQUEST_CATEGORY = "SERVICE_MANAGEMENT.NETWORK_INTERFACE_CONFIG"
IFACE_PROC_WORK_REQUEST_ACTION = "apply"
IFACE_PROC_WORK_REQUEST_PRIORITY = 70
KERNEL_PARAMS_WORK_REQUEST_CATEGORY = "SERVICE_MANAGEMENT.NETWORK_KERNEL_PARAM_CONFIG"
KERNEL_PARAMS_WORK_REQUEST_ACTION = "apply"
KERNEL_PARAMS_WORK_REQUEST_PRIORITY = 70
SERVICES_DB_PATH = DB_DIR / "services.db"
DNSMASQ_DB_PATH = DB_DIR / "dnsmasq.db"
DNSMASQ_LEASES_PATH = Path("/var/lib/dnsmasq/dnsmasq.leases")
DNSMASQ_CONF_PATH = CONF_DIR / "dnsmasq.conf"
DNSMASQ_DNS_PORT = 53
DNSMASQ_DOMAIN_LABEL_PATTERN = r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
DNSMASQ_MAC_ADDRESS_PATTERN = r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$"
DNSMASQ_BOOL_DEFAULTS = {
    "expand_hosts": True,
    "domain_needed": True,
    "bogus_priv": True,
    "dhcp_authoritative": True,
}
DNSMASQ_ALL_INTERFACES_TOKEN = "__all__"
DNSMASQ_INTERFACE_CONFIG_PREFIX = "# armfirewall-interface-config="
LATENCY_DB_PATH = DB_DIR / "latency.db"
LINKFAILOVER_DB_PATH = DB_DIR / "linkfailover.db"
POLICY_ROUTING_DB_PATH = DB_DIR / "policy-routing.db"
LIBRESWAN_DB_PATH = DB_DIR / "libreswan.db"
RUNTIME_SETTINGS_DB_PATH = DB_DIR / "runtime_settings.db"

BIRD_DB_PATH = DB_DIR / "bird.db"
BIRD_DDL_PATH = DB_DIR / "ddl" / "bird.ddl"
SYSTEM_DDL_PATH = DB_DIR / "ddl" / "system.ddl"
NETWORK_DDL_PATH = DB_DIR / "ddl" / "network.ddl"
BIRD_CONFIG_PATH = CONF_DIR / "bird.conf"
BIRD_LOG_PATH = LOG_DIR / "bird.out.log"
BIRD_ERR_LOG_PATH = LOG_DIR / "bird.err.log"
BIRD_ANY_INTERFACE = "*"
BIRD_DEFAULT_CHANNEL_TABLE_NAME = "main"
BIRD_DEFAULT_ROUTER_ID = "192.0.2.1"
BIRD_DEFAULT_HOSTNAME = "armfirewall"
BIRD_IMPORT_EXPORT_VALUES = {"all", "none"}
BIRD_CHANNEL_FAMILIES = {"ipv4", "ipv6", "ipv4/ipv6"}
BIRD_RIP_VERSIONS = {"1", "2", "ng"}
BIRD_RIP_MODES = {"multicast", "broadcast"}
BIRD_RIP_AUTHENTICATIONS = {"none", "plaintext", "cryptographic"}
BIRD_BGP_SESSION_TYPES = {"auto", "ibgp", "ebgp"}

COLLECTORD_LOG_SOURCE = "collectord.py"
IFACEMGMTD_LOG_SOURCE = "ifacemgmtd.py"
COLLECTORD_SCHEDULER_TICK_SECONDS = int(os.environ.get("ARMFW_COLLECTORD_SCHEDULER_TICK", "1"))
COLLECTORD_BIRD_PROTOCOLS_INTERVAL_SECONDS = int(
    os.environ.get("ARMFW_COLLECTORD_BIRD_PROTOCOLS_INTERVAL", "5")
)
COLLECTORD_BIRD_COMMAND_TIMEOUT_SECONDS = int(
    os.environ.get("ARMFW_COLLECTORD_BIRD_COMMAND_TIMEOUT", "5")
)
COLLECTORD_BIRD_COMMAND_RETENTION = int(
    os.environ.get("ARMFW_COLLECTORD_BIRD_COMMAND_RETENTION", "500")
)
COLLECTORD_BIRDCL_PATH = os.environ.get("ARMFW_BIRDCL_PATH", "/usr/sbin/birdcl")
COLLECTORD_BIRD_SHOW_PROTOCOLS_COMMAND = [COLLECTORD_BIRDCL_PATH, "show", "protocols"]
COLLECTORD_BIRD_RIP_DIAGNOSTIC_COMMANDS = (
    ("status", [COLLECTORD_BIRDCL_PATH, "show", "protocols", "all", "rip1"]),
    ("learned-routes", [COLLECTORD_BIRDCL_PATH, "show", "route", "protocol", "rip1"]),
    ("exported-routes", [COLLECTORD_BIRDCL_PATH, "show", "route", "export", "rip1"]),
)
COLLECTORD_IFACE_INTERVAL_SECONDS = int(os.environ.get("ARMFW_COLLECTORD_IFACE_INTERVAL", "10"))
COLLECTORD_IFACE_PROC_ITEMS = (
    ("ipv4", "forwarding", "Enables IPv4 packet forwarding on this interface."),
    ("ipv4", "rp_filter", "Controls reverse path filtering for IPv4 packets."),
    ("ipv4", "accept_redirects", "Controls whether ICMP redirect messages are accepted."),
    ("ipv4", "send_redirects", "Controls whether ICMP redirect messages are sent."),
    ("ipv4", "accept_source_route", "Controls whether source-routed IPv4 packets are accepted."),
    ("ipv4", "log_martians", "Controls logging of packets with impossible or suspicious source addresses."),
    ("ipv4", "arp_filter", "Controls whether ARP replies are filtered according to the route table."),
    ("ipv4", "arp_ignore", "Controls when the kernel replies to ARP requests for local addresses."),
    ("ipv4", "arp_announce", "Controls how local source IP addresses are announced in ARP requests."),
    ("ipv6", "disable_ipv6", "Controls whether IPv6 is disabled on this interface."),
    ("ipv6", "forwarding", "Enables IPv6 packet forwarding on this interface."),
    ("ipv6", "accept_redirects", "Controls whether ICMPv6 redirect messages are accepted."),
    ("ipv6", "accept_ra", "Controls whether IPv6 Router Advertisement messages are accepted."),
)

ADAM_DATASET_DIR = ROOT_DIR / "daemons" / "adamd" / "datasets"
ADAM_DATASET_MAX_BYTES = 5 * 1024 * 1024
ADAM_DATASET_MAX_ROWS = 100_000
ADAM_DATASET_REQUIRED_COLUMNS = ("text", "label")
ADAM_DATASET_TYPES = {"training", "testing"}
ADAM_DATASET_CATEGORIES = {
    "adam_misc": "Adam Misc",
    "firewall": "Firewall",
    "greetings": "Greetings",
    "ner": "NER",
}
ADAM_TEXT_CLASSIFIER_DATASET_CATEGORIES = {"adam_misc", "firewall", "greetings"}
ADAM_MODELS_DIR = ROOT_DIR / "daemons" / "adamd" / "models"
ADAM_CHARTS_DIR = ROOT_DIR / "daemons" / "adamd" / "charts"
ADAM_DELETE_STAGING_DIR = ROOT_DIR / "daemons" / "adamd" / ".delete-staging"
ADAM_TEXT_CLASSIFIER_MODEL_FILENAME = "text_classifier.joblib"
ADAM_TEXT_CLASSIFIER_MODEL_PATH = (
    ADAM_MODELS_DIR / ADAM_TEXT_CLASSIFIER_MODEL_FILENAME
)
ADAM_TEXT_CLASSIFIER_MAX_ITERATIONS = 1_000
ADAM_TEXT_CLASSIFIER_RANDOM_STATE = 42
ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE = 0.58
ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE = 0.40
ADAM_CHECK_FIREWALL_RULE_INTENT = "check_firewall_rule"
ADAM_CREATE_FIREWALL_BLOCK_RULE_INTENT = "create_firewall_block_rule"
ADAM_SPOKEN_PORT_MAX_TOKENS = 8
ADAM_TEXT_CLASSIFIER_CHART_DPI = 120
ADAM_TEXT_CLASSIFIER_CHART_FILENAME_PREFIX = "text_classifier"
ADAM_SPEECH_LANGUAGE_PT_BR = "pt-BR"
ADAM_SPEECH_LANGUAGE_EN_US = "en-US"
ADAM_WAKE_WORD_PT_BR = "Adão"
ADAM_WAKE_WORD_EN_US = "Adam"
ADAM_WAKE_WORD_ALIASES_PT_BR = ("Adão", "Adan")
ADAM_WAKE_WORD_ALIASES_EN_US: tuple[str, ...] = ()
ADAM_WAKE_PROFILE_KEY_PT_BR = "default"
ADAM_WAKE_PROFILE_KEY_EN_US = "en-US:adam"
ADAM_SPEECH_LANGUAGE = ADAM_SPEECH_LANGUAGE_EN_US
ADAM_WAKE_WORD = ADAM_WAKE_WORD_EN_US
ADAM_WAKE_WORD_ALIASES = ADAM_WAKE_WORD_ALIASES_EN_US
ADAM_WAKE_PROFILE_KEY = ADAM_WAKE_PROFILE_KEY_EN_US
ADAM_WAKE_WORD_MIN_CONFIDENCE = 0.55
ADAM_WAKE_AUDIO_PROCESSOR_URL = "/static/js/adam_audio_processor.js?v=20260816-whisper"
ADAM_WAKE_DETECTOR_WORKER_URL = "/static/js/adam_wake_detector_worker.js?v=20260803-server-profile"
ADAM_WAKE_ENROLLMENT_SAMPLES = 5
ADAM_WAKE_ENROLLMENT_DURATION_MS = 1_800
ADAM_WAKE_DETECTION_INTERVAL_MS = 250
ADAM_WAKE_DETECTION_STREAK = 2
ADAM_WAKE_DETECTION_THRESHOLD_MULTIPLIER = 1.6
ADAM_WAKE_PRE_ROLL_MS = 1_000
ADAM_COMMAND_MIN_CAPTURE_MS = 1_500
ADAM_COMMAND_SAMPLE_RATE = 16_000
ADAM_COMMAND_TRAILING_SILENCE_MS = 2_500
ADAM_COMMAND_SILENCE_THRESHOLD = 0.004
ADAM_COMMAND_TIMEOUT_MS = 20_000
ADAM_TRANSCRIPTION_MAX_CHARS = 2_000
ADAM_TRANSCRIPTION_MAX_BYTES = 8 * 1024 * 1024
ADAM_WHISPER_MODEL_NAME = "base.en"
ADAM_WHISPER_LANGUAGE = "en"
ADAM_WHISPER_DEVICE = "cpu"
ADAM_WHISPER_COMPUTE_TYPE = "int8"
ADAM_WHISPER_INITIAL_PROMPT = (
    "Firewall administration commands. Use terms such as Adam, firewall, port, "
    "TCP, UDP, allow, block, check, source, destination, and interface."
)
ADAM_WEBSOCKET_CLOSE_UNAUTHORIZED = 4401
ADAM_WEBSOCKET_CLOSE_FORBIDDEN = 4403
ADAM_WEBSOCKET_POLL_INTERVAL_SECONDS = 2
ADAM_WEBSOCKET_MAX_PROCESSED_REQUESTS = 128
ADAM_WEBSOCKET_LOG_SOURCE = "adam-websocket"
ADAM_WEBSOCKET_REPEAT_PROMPTS = (
    "Sir, I didn't understand. Can you repeat, please?",
    "I didn't get your point, Sir. Come again?",
    "Sorry, Sir. Could you say that again?",
    "I'm not sure, Sir. Could you repeat that?",
    "Could you repeat that for me, Sir?",
)
ADAM_LISTENING_STORAGE_KEY = "armfirewall.adam.listening-enabled"
ADAM_DB_PATH = DB_DIR / "adam.db"
ADAM_DDL_PATH = DB_DIR / "ddl" / "adam.ddl"
ADAM_WORK_REQUEST_CATEGORY = "ADAM.MODEL_TRAINING"
ADAM_WORK_REQUEST_ACTION = "train"
ADAM_WORK_REQUEST_DELETE_ACTION = "delete"
ADAM_WORK_REQUEST_TARGET = "model_training"
ADAM_LOG_SOURCE = "adamd/adamd.py"
ADAM_SYSTEMD_RUN_PATH = Path("/usr/bin/systemd-run")
ADAM_TRAINING_CPU_QUOTA_PERCENT = 25
ADAM_TRAINING_MEMORY_HIGH_BYTES = 384 * 1024 * 1024
ADAM_TRAINING_MEMORY_MAX_BYTES = 512 * 1024 * 1024
ADAM_TRAINING_TASKS_MAX = 32
ADAM_TRAINING_NICE = 10
ADAM_TRAINING_MAX_THREADS = 1
ADAM_TRAINING_RUNTIME_MAX_SECONDS = 240
ADAM_TRAINING_OOM_POLICY = "stop"

RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"

ADGUARD_HOME_SERVICE_NAME = "adguardhome"
ADGUARD_HOME_ARCHIVE_URL = "https://github.com/AdguardTeam/AdGuardHome/releases/latest/download/AdGuardHome_linux_arm64.tar.gz"
ADGUARD_HOME_DIR = ROOT_DIR / "daemons" / "adguardhome"
ADGUARD_HOME_BINARY = ADGUARD_HOME_DIR / "AdGuardHome"
ADGUARD_HOME_WORK_DIR = ADGUARD_HOME_DIR / "data"
ADGUARD_HOME_WEB_HOST = "127.0.0.1"
ADGUARD_HOME_WEB_PORT = 3001
ADGUARD_HOME_DNS_BIND_HOSTS = ("127.0.0.1",)
ADGUARD_HOME_DNS_PORT = 53
ADGUARD_HOME_CONFIG_PATH = ADGUARD_HOME_WORK_DIR / "AdGuardHome.yaml"
