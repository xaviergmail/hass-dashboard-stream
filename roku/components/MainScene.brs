sub init()
    ' The add-on serves a single cached JPEG, avoiding Roku HLS buffering.
    m.snapshotUrl = "http://dashboard-streams.local:8099/snapshot.jpg"
    m.poster = m.top.FindNode("poster")
    m.status = m.top.FindNode("status")
    m.timer = m.top.FindNode("refreshTimer")
    m.haveFrame = false

    m.poster.ObserveField("loadStatus", "onPosterStatus")
    m.timer.ObserveField("fire", "refreshSnapshot")
    m.timer.control = "start"
    refreshSnapshot()
end sub

sub refreshSnapshot()
    ' Query-string cache busting prevents Roku from reusing an old JPEG.
    stamp = CreateObject("roDateTime").AsSeconds()
    m.poster.setField("uri", m.snapshotUrl + "?t=" + StrI(stamp, 10))
end sub

sub onPosterStatus(event as Object)
    status = event.GetData()
    if status = "ready"
        m.haveFrame = true
        m.status.text = ""
    else if status = "failed" and not m.haveFrame
        m.status.text = "Dashboard snapshot unavailable"
    end if
end sub
