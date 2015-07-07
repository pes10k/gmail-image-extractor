jQuery(function ($) {

    var prog_hidden = true,
        loc = window.location,
        $prog_container = $(".progress"),
        $prog = $(".progress-bar"),
        $email = $("#email"),
        $pass = $("#password"),
        $submit = $("#submit"),
        $auth_form = $("#auth-form"),
        $auth_fields = $auth_form.find(":input"),
        $alert = $(".alert"),
        $sync_form = $("#sync-form"),
        $confim_form = $("#confirm-form"),
        $no_confirm_bttn = $confim_form.find("[type=cancel]"),
        rewrite_index = 0,
        rewrite_total = 0,
        feedback,
        num_messages,
        update_progress,
        hide_progress,
        ws = new WebSocket("ws://" + loc.host + (loc.port ? (":" + loc.port) : "")) + "/ws");

    hide_progress = function () {
        $prog_container.fadeOut();
        prog_hidden = true;
    };

    update_progress = function (cur, max) {

        if (prog_hidden) {
            $prog_container.fadeIn();
            prog_hidden = false;
        }

        if (!cur && !max) {

            $prog_container.addClass("progress-striped").addClass("active");
            $prog.attr("aria-valuenow", 1)
                .attr("aria-valuemax", 1)
                .css("width", "100%");

        } else {

            $prog_container.removeClass("progress-striped").removeClass("active");
            $prog.attr("aria-valuenow", cur)
                .attr("aria-valuemax", max)
                .css("width", ((cur / max) * 100) + "%");
        }
    };

    feedback = function (msg, additional_message) {

        $alert.removeClass("alert-info").removeClass("alert-warning");
        $alert.show();

        if (msg.ok) {

            $alert.addClass("alert-info");

        } else {

            $alert.addClass("alert-warning");

        }

        if (additional_message) {

            $alert.html("<p>" + msg.msg + "</p><p>" + additional_message + "</p>");

        } else {

            $alert.text(msg.msg);

        }
    };

    $auth_form.submit(function () {

        var params = JSON.stringify({
            "email": $email.val(),
            "pass": $pass.val(),
            "type": "connect",
            "limit": 0,
            "simultaneous": 10,
            "rewrite": 1
        });

        $auth_fields.attr("disabled", "disabled");
        ws.send(params);

        return false;
    });

    $sync_form.submit(function () {

        var params = JSON.stringify({
            "type": "sync"
        });

        $(this).find("[type=submit]").attr("disabled", "disabled");
        ws.send(params);

        return false;
    });

    $confim_form.submit(function () {

        var params = JSON.stringify({
            "type": "confirm",
        });

        $(this).find("button").attr("disabled", "disabled");
        ws.send(params);

        return false;
    });

    $no_confirm_bttn.click(function () {

        feedback({msg: "Thank you for your participation in this study."});
        $confim_form.fadeOut();
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

            case "download-complete":
                feedback(msg, "Please delete any attachments you'd like removed from your GMail account from " + window.gmail.home);
                hide_progress();
                $sync_form.fadeIn();
                break;

            case "file-checking":
                feedback(msg);
                update_progress();
                $sync_form.fadeOut();
                break;

            case "file-checked":
                rewrite_total = msg.num;
                hide_progress();
                $alert.hide();
                $confim_form
                    .fadeIn()
                    .find("p")
                        .text("Are you sure you want to remove " + rewrite_total + " images from your email account?  This action is irreversable.");
                break;

            case "removing":
                $confim_form.fadeOut();
                feedback(msg);
                update_progress(++rewrite_index, rewrite_total);
                break;

            case "removed":
                feedback(msg);
                break;

            case "finished":
                feedback(msg);
                hide_progress();
                break;
        }
    };
});
