"""Home Assistant Integration Example

This file shows example Home Assistant automations and configurations
for integrating with HA Print Monitor.

SETUP:

1. Install Home Assistant webhook integration if not already installed
2. Go to Settings > Devices & Services > Create Automation
3. Create automations for notifications (examples below)
4. Configure the app with your entity IDs
"""

# Example 1: Basic Notification Automation
# This automation sends a simple notification when triggered
automation_notification:
  - alias: "HA Print Monitor Notification"
    description: "Forward print monitor alerts to mobile"
    trigger:
      platform: webhook
      webhook_id: "ha-print-monitor-webhook"
    action:
      service: notify.mobile_app_phone
      data:
        title: "{{ trigger.json.title }}"
        message: "{{ trigger.json.message }}"
        data:
          image: "{{ trigger.json.data.image }}"
          actions: "{{ trigger.json.data.actions }}"


# Example 2: Script to handle pause action
script:
  handle_print_pause:
    description: "Handle pause action from print monitor"
    sequence:
      - service: button.press
        target:
          entity_id: button.printer_pause_print
      - service: notify.mobile_app_phone
        data:
          title: "Print Paused"
          message: "Printer pause requested"


# Example 3: Automation to monitor printer state changes
automation_state_change:
  - alias: "Track Printer Status Changes"
    description: "Log printer state changes"
    trigger:
      platform: state
      entity_id: sensor.printer_status
    action:
      service: system_log.write
      data:
        level: info
        logger: ha_print_monitor
        message: "Printer state changed to {{ states('sensor.printer_status') }}"


# Example 4: Create Long-Lived Access Token (via code)
# In Home Assistant Developer Tools > Python Shell:
# import secrets
# token = secrets.token_urlsafe(32)
# print(f"Token: {token}")


# Example 5: Mock Camera Entity
# If you don't have a real camera, create one:
camera:
  - platform: generic
    name: "Printer Camera"
    still_image_url: "http://192.168.1.50:8080/snapshot"
    verify_ssl: false


# Example 6: Mock Printer Status Sensor
# If using a Prusa with API:
sensor:
  - platform: rest
    name: "Prusa Print Status"
    resource: "http://192.168.1.50/api/printer/status"
    value_template: "{{ value_json.state }}"
    unique_id: "prusa_print_status"


# Example 7: Pause Button using REST
button:
  - platform: rest
    name: "Prusa Pause Print"
    url: "http://192.168.1.50/api/printer/pause"
    method: POST
    unique_id: "prusa_pause"


# Example 8: Mobile App Notification with Actions
# This is what HA Print Monitor sends:
notification_payload_example:
  title: "🖨️ Possible 3D print issue detected"
  message: |
    Spaghetti failure suspected with 91% certainty.
    Auto-pause in 15 minutes unless ignored.
  data:
    image: "https://app.example.com/captures/event_123.jpg"
    actions:
      - action: "URI"
        title: "Pause Print"
        uri: "https://app.example.com/api/actions/pause?event_id=event_123&token=..."
      - action: "URI"
        title: "Ignore"
        uri: "https://app.example.com/api/actions/ignore?event_id=event_123&token=..."
      - action: "URI"
        title: "Snooze 15m"
        uri: "https://app.example.com/api/actions/snooze?event_id=event_123&token=..."


# Example 9: YAML-based Automation File
# Add this to automations.yaml:

# Print monitor auto-pause notification
- alias: "Print Monitor - Issue Detected"
  description: "Alert when print issue detected"
  trigger:
    platform: webhook
    webhook_id: "print-monitor-webhook"
  condition:
    condition: template
    value_template: "{{ trigger.json.severity in ['high', 'critical'] }}"
  action:
    - service: notify.mobile_app_all_phones
      data:
        title: "⚠️ Print Issue: {{ trigger.json.issue_type }}"
        message: |
          Certainty: {{ trigger.json.certainty }}%
          {{ trigger.json.message }}
        data:
          image: "{{ trigger.json.image_url }}"
          actions:
            - action: "PAUSE_PRINT"
              title: "Pause Now"
            - action: "DISMISS"
              title: "Dismiss Alert"


# Example 10: Service Call Configuration
# Reference in config.yaml:
home_assistant:
  url: "http://homeassistant.local:8123"
  token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  camera_entity: "camera.prusa_camera"
  printer_state_entity: "sensor.prusa_print_status"
  printing_states:
    - "printing"
    - "paused"
  pause_service:
    # Method 1: Direct button press
    domain: "button"
    service: "press"
    target: "button.prusa_pause_print"
    data: {}
    
    # Method 2: Call generic service
    # domain: "script"
    # service: "handle_print_pause"
    # target: null
    # data: {}
    
    # Method 3: REST call
    # domain: "rest"
    # service: "pause_printer"
    # target: null
    # data:
    #   host: "192.168.1.50"
