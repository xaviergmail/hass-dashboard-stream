sub init()
    m.snapshotUrl = "http://dashboard-streams.local:8099/snapshot.png"
    m.posterA = m.top.FindNode("posterA")
    m.posterB = m.top.FindNode("posterB")
    m.status = m.top.FindNode("status")
    m.timer = m.top.FindNode("refreshTimer")
    m.activePoster = ""
    m.loadingPoster = ""
    m.loading = false
    m.haveFrame = false

    m.posterA.ObserveField("loadStatus", "onPosterAStatus")
    m.posterB.ObserveField("loadStatus", "onPosterBStatus")
    m.timer.ObserveField("fire", "refreshSnapshot")
    m.timer.control = "start"
    refreshSnapshot()
end sub

sub refreshSnapshot()
    if m.loading then return

    target = "A"
    if m.activePoster = "A"
        target = "B"
    else if m.activePoster = "B"
        target = "A"
    end if

    stamp = CreateObject("roDateTime").AsSeconds()
    url = m.snapshotUrl + "?t=" + StrI(stamp, 10)
    m.loadingPoster = target
    m.loading = true
    if target = "A"
        m.posterA.setField("uri", url)
    else
        m.posterB.setField("uri", url)
    end if
end sub

sub onPosterAStatus(event as Object)
    onPosterStatus("A", event.GetData())
end sub

sub onPosterBStatus(event as Object)
    onPosterStatus("B", event.GetData())
end sub

sub onPosterStatus(which as String, status as String)
    if which <> m.loadingPoster then return

    if status = "ready"
        if which = "A"
            m.posterA.setField("visible", true)
            m.posterB.setField("visible", false)
        else
            m.posterA.setField("visible", false)
            m.posterB.setField("visible", true)
        end if
        m.activePoster = which
        m.loading = false
        m.haveFrame = true
        m.status.text = ""
    else if status = "failed"
        m.loading = false
        if not m.haveFrame
            m.status.text = "Dashboard snapshot unavailable"
        end if
    end if
end sub
