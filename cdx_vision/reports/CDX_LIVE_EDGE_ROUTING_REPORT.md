# Live-edge routing

Auto-right runs only when the current CDX marker is absent and the level text is missing.

If the marker is already in the capture, the route is visible extraction and Ctrl+Right is not sent.

If a pan is attempted and the chart crop does not move, navigation stops after that one command. The reason is `VISION_ALREADY_AT_LIVE_EDGE`. Further right-arrow attempts are not sent.

A vertical clip is reported only when a detected line sits on the top or bottom edge of the chart pane. That did not happen on the saved MNQ capture. The missing targets are not classified as a horizontal pan failure.
