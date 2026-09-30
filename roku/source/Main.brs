sub Main()
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    screen.CreateScene("MainScene")
    screen.Show()

    while true
        message = Wait(0, port)
        if Type(message) = "roSGScreenEvent" and message.IsScreenClosed()
            return
        end if
    end while
end sub
