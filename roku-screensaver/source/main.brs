Function RunScreenSaver(params As Object) As Object
    screen = CreateObject("roSGScreen")
    port = CreateObject("roMessagePort")
    screen.SetMessagePort(port)
    screen.CreateScene("ScreensaverScene")
    screen.Show()

    while true
        message = Wait(0, port)
        if Type(message) = "roSGScreenEvent" and message.IsScreenClosed()
            exit while
        end if
    end while

    screen.Close()
End Function
