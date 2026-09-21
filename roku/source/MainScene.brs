sub init()
    ' The add-on serves a single cached JPEG, avoiding Roku HLS buffering.
    m.snapshotUrl = "http://homeassistant:8099/snapshot.jpg"
    m.poster = m.top.FindNode("poster")
    m.status = m.top.FindNode("status")
    m.timer = m.top.FindNode("refreshTimer")

    m.poster.ObserveField("loadStatus", "onPosterStatus")
    m.timer.ObserveField("fire", "refreshSnapshot")
    m.timer.Control = "start"
    refreshSnapshot()
end sub

sub refreshSnapshot()
    ' Query-string cache busting prevents Roku from reusing an old JPEG.
    stamp = CreateObject("roTimespan").TotalMilliseconds()
    m.poster.Uri = m.snapshotUrl + "?t=" + StrI(stamp)
end sub

sub onPosterStatus(event as Object)
    status = event.GetData()
    if status = "ready"
        m.status.Text = ""
    else if status = "failed"
        m.status.Text = "Dashboard snapshot unavailable"
    else if status = "loading"
        m.status.Text = "Loading Dashboard Streams..."
    end if
end sub
