import dataclasses
import datetime
import pathlib
import threading
import typing

import faery
import neuromorphic_drivers as nd
import numpy as np

import ui


@dataclasses.dataclass
class Recording:
    path: pathlib.Path
    encoder: faery.csv.Encoder
    frames_metadata: typing.TextIO
    frame_index: int


def camera_thread_target(
    device: nd.inivation_davis346.InivationDavis346DeviceOptional,
    event_displays: tuple[ui.EventDisplay, ui.EventDisplay],
    frame_display: ui.FrameDisplay,
    context: dict[str, typing.Any],
):
    current_recording: typing.Optional[Recording] = None
    for status, packet in device:
        if not context["running"]:
            break
        if current_recording is None:
            if context["recording"] is not None:
                current_recording = context["recording"]
        else:
            if (
                context["recording"] is None
                or current_recording.path != context["recording"].path
            ):
                current_recording.encoder.__exit__(None, None, None)
                current_recording.frames_metadata.close()
                current_recording = context["recording"]
        if packet is not None:
            if packet.polarity_events is not None:
                if current_recording is not None:
                    current_recording.encoder.write(packet.polarity_events)
                assert status.ring is not None and status.ring.current_t is not None
                for event_display in event_displays:
                    event_display.push(
                        events=packet.polarity_events,
                        current_t=status.ring.current_t,
                    )
            elif status.ring is not None and status.ring.current_t is not None:
                for event_display in event_displays:
                    event_display.push(
                        events=np.array([]),
                        current_t=status.ring.current_t,
                    )
            if len(packet.frames) > 0:
                if current_recording is not None:
                    for frame in packet.frames:
                        with open(
                            current_recording.path
                            / "frames"
                            / f"{current_recording.frame_index:06d}.raw",
                            "wb",
                        ) as frame_file:
                            frame_file.write(frame.pixels.tobytes())
                        current_recording.frames_metadata.write(
                            f"{current_recording.frame_index:06d},{frame.start_t},{frame.exposure_start_t},{frame.exposure_end_t},{frame.t}\n"
                        )
                        current_recording.frame_index += 1
                frame_display.push(packet.frames[-1].pixels)


if __name__ == "__main__":
    nd.print_device_list()
    configuration = nd.inivation_davis346.Configuration()
    device = nd.open(
        configuration=configuration,
        iterator_timeout=1.0 / 60.0,
    )
    print(device.serial(), device.properties())

    recordings = pathlib.Path(__file__).resolve().parent / "data"
    recordings.mkdir(exist_ok=True)

    transparent_on_colormap: list[str] = []
    for index, color in enumerate(ui.DEFAULT_ON_COLORMAP):
        transparent_on_colormap.append(
            '"#{:02X}{:02X}{:02X}{:02X}"'.format(
                int(round(index / (len(ui.DEFAULT_ON_COLORMAP) - 1) * 255)),
                color.red(),
                color.green(),
                color.blue(),
            )
        )
    transparent_off_colormap: list[str] = []
    for index, color in enumerate(ui.DEFAULT_OFF_COLORMAP):
        transparent_off_colormap.append(
            '"#{:02X}{:02X}{:02X}{:02X}"'.format(
                int(round(index / (len(ui.DEFAULT_OFF_COLORMAP) - 1) * 255)),
                color.red(),
                color.green(),
                color.blue(),
            )
        )

    biases_names = set(dataclasses.asdict(configuration.biases).keys())

    def to_python(key: str, value: typing.Any):
        if key == "exposure":
            configuration.exposure_us = int(value)
            device.update_configuration(configuration)
        elif key in biases_names:
            setattr(configuration.biases, key, int(value))
            device.update_configuration(configuration)
        elif key == "start_recording":
            name = (
                datetime.datetime.now(tz=datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
                .replace(":", "-")
            )
            path = recordings / name
            path.mkdir(exist_ok=True)
            (path / "frames").mkdir(exist_ok=True)
            frames_metadata = open(path / "frames_metadata.csv", "w")
            frames_metadata.write(f"index,start_t,exposure_start_t,exposure_end_t,t\n")
            context["recording"] = Recording(
                path=path,
                encoder=faery.csv.Encoder(
                    path=path / f"{name}.csv",
                    separator=b","[0],
                    header=True,
                    dimensions=(346, 360),
                    enforce_monotonic=True,
                ),
                frames_metadata=frames_metadata,
                frame_index=0,
            )
        elif key == "stop_recording":
            context["recording"] = None
        else:
            print(f"Unknown to_python key: {key}")

    biases = ""
    for name, value in dataclasses.asdict(configuration.biases).items():
        biases += f"""
        RowLayout {{
            spacing: 5
            Label {{
                Layout.minimumWidth: 100
                horizontalAlignment: Text.AlignRight
                text: "{name}"
            }}
            SpinBox {{
                from: 0
                to: 2040
                stepSize: 1
                editable: true
                value: {value}
                onValueChanged: to_python.{name} = value
            }}
        }}
        """

    app = ui.App(
        qml=f"""
        import QtQuick
        import QtQuick.Controls
        import QtQuick.Layouts 1.2
        import NeuromorphicDrivers

        Window {{
            width: 1280
            height: 720
            color: "#292929"
            property var overlayEventsOnFrames: false

            ColumnLayout {{
                anchors.fill: parent
                spacing: 0

                RowLayout {{
                    spacing: 0

                    Rectangle {{
                        id: container
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "transparent"

                        FrameDisplay {{
                            width: container.width
                            height: container.height
                            sensor_size: "{device.properties().width}x{device.properties().height}"
                            mode: "L"
                            dtype: "u2"
                        }}

                        EventDisplay {{
                            id: eventDisplayOverlay
                            visible: overlayEventsOnFrames
                            width: container.width
                            height: container.height
                            objectName: "event-display-overlay"
                            sensor_size: "{device.properties().width}x{device.properties().height}"
                            style: "exponential"
                            tau: 100000
                            on_colormap: [{','.join(transparent_on_colormap)}]
                            off_colormap: [{','.join(transparent_off_colormap)}]
                            clear_background: false
                        }}
                    }}

                    EventDisplay {{
                        id: eventDisplayStandalone
                        visible: !overlayEventsOnFrames
                        objectName: "event-display-standalone"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        sensor_size: "{device.properties().width}x{device.properties().height}"
                        style: "exponential"
                        tau: 100000
                    }}
                }}

                ColumnLayout {{
                    id: recordingContainer
                    property var recording: false
                    property var actionHash: 0
                    Layout.margins: 10
                    Label {{
                        text: "Record"
                        color: "#AAAAAA"
                    }}
                    RowLayout {{
                        spacing: 10
                        Button {{
                            text: "Start recording"
                            onClicked: {{
                                recordingContainer.recording = true;
                                ++recordingContainer.actionHash;
                                to_python.start_recording = recordingContainer.actionHash;
                            }}
                            enabled: !recordingContainer.recording
                        }}
                        Button {{
                            text: "Stop recording"
                            onClicked: {{
                                recordingContainer.recording = false;
                                ++recordingContainer.actionHash;
                                to_python.stop_recording = recordingContainer.actionHash;
                            }}
                            enabled: recordingContainer.recording
                        }}
                    }}
                }}

                ColumnLayout {{
                    Layout.margins: 10
                    Label {{
                        text: "Display properties"
                        color: "#AAAAAA"
                    }}
                    RowLayout {{
                        spacing: 10

                        Switch {{
                            text: "Overlay events on frames"
                            checked: overlayEventsOnFrames
                            onClicked: overlayEventsOnFrames = checked
                        }}

                        RowLayout {{
                            spacing: 5
                            Label {{
                                text: "Style"
                            }}
                            ComboBox {{
                                model: ["Exponential", "Linear", "Window"]
                                currentIndex: 0
                                onCurrentIndexChanged: {{
                                    eventDisplayOverlay.style = model[currentIndex].toLowerCase()
                                    eventDisplayStandalone.style = model[currentIndex].toLowerCase()
                                }}
                            }}
                        }}

                        RowLayout {{
                            spacing: 5
                            Label {{
                                text: "𝜏 (ms)"
                            }}
                            SpinBox {{
                                from: 1
                                to: 100000
                                stepSize: 1
                                editable: true
                                value: {int(round(ui.DEFAULT_TAU / 1000))}
                                onValueChanged: {{
                                    eventDisplayOverlay.tau = value * 1000
                                    eventDisplayStandalone.tau = value * 1000
                                }}
                            }}
                        }}
                    }}

                    Label {{
                        text: "Camera properties"
                        Layout.topMargin: 10
                        color: "#AAAAAA"
                    }}

                    RowLayout {{
                        spacing: 5
                        Label {{
                            Layout.minimumWidth: 100
                            horizontalAlignment: Text.AlignRight
                            text: "Exposure (µs)"
                        }}
                        SpinBox {{
                            from: 1
                            to: 8000000
                            stepSize: 1
                            editable: true
                            value: {configuration.exposure_us}
                            onValueChanged: to_python.exposure = value
                        }}
                    }}

                    GridLayout {{
                        columns: 3
                        {biases}
                    }}
                }}
            }}
        }}
        """,
        to_python=to_python,
    )

    event_displays = (
        app.event_display(object_name="event-display-overlay"),
        app.event_display(object_name="event-display-standalone"),
    )
    frame_display = app.frame_display()
    context = {"running": True, "recording": None}
    camera_thread = threading.Thread(
        target=camera_thread_target,
        args=(device, event_displays, frame_display, context),
    )
    camera_thread.start()
    app.run()
    context["running"] = False
    camera_thread.join()
    device.__exit__(None, None, None)
