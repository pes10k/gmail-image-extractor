jQuery(function ($) {

    var prog_hidden = true,
        $prog_container = $(".progress"),
        $prog = $(".progress-bar"),
        $email = $("#email"),
        $pass = $("#password"),
        $submit = $("#submit"),
        $auth_fields = $email.add($pass).add($submit),
        $auth_form = $("#auth-form"),
        $alert = $(".alert"),
        feedback,
        num_messages,
        update_progress,
        ws = new WebSocket("ws://localhost:8888/ws");

    update_progress = function (cur, max) {

        if (prog_hidden) {
            $prog_container.show();
            prog_hidden = false;
        }

        $prog.attr("aria-valuenow", cur)
            .attr("aria-valuemax", max)
            .css("width", ((cur / max) * 100) + "%");
    };

    feedback = function (msg) {
        $alert.removeClass("alert-info").removeClass("alert-warning");
        $alert.show();

        if (msg.ok) {
            $alert.addClass("alert-info");
        } else {
            $alert.addClass("alert-warning");
        }

        $alert.text(msg.msg);
    };

    $form.submit(function () {

        var params = JSON.stringify({
            "email": $email.val(),
            "pass": $pass.val(),
            "type": "connect"
        });

        $auth_fields.attr("disabled", "disabled");
        ws.send(params);

        return false;
    });

    ws.onmessage = function (evt) {
        var msg = JSON.parse(evt.data);

        switch (msg['type']) {

            case "connect":
                feedback(msg);
                if (!msg.ok) {
                    $auth_fields.removeAttr("disabled");
                } else {
                    $auth_form.fadeOut();
                }
                break;

            case "count":
                feedback(msg);
                num_messages = msg.num;
                break;

            case "downloading":
                feedback(msg);
                update_progress(msg.num, num_messages);
                break;
        }

        console.log(msg);
    };
});
