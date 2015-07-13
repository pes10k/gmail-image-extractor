
jQuery(function ($) {

  var prog_hidden = true,
    results_hidden = true, //added
    loc = window.location,
    $prog_container = $(".progress"),
    $prog = $(".progress-bar"),
    $results_container = $(".results"), //added
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
  update_results, //added 
  img_id = 0,
  hide_results, //added
  selected_imgs = [],
    ws = new WebSocket("ws://" + loc.host + "/ws");

  //added
  hide_results = function () {

    $results_container.fadeOut();
    results_hidden = true;
  };

  //displays images in the browser as they are found in the users mailbox
  update_results = function (msg_id, img_id, enc_img, signed_req) {

    if (results_hidden) {

      $results_container.show();
      results_hidden = false;
    }

    //decode image from base64 to small image to display in img tag
    var img = new Image();
    img.src = 'data:image/jpeg;base64,' + enc_img;
    img.height = 500;
    img.width = 500;

    //create thumbnail for image to be displayed in
    //create a unique img_id for the purpose of selecting each image
    $results_container.append('<div class="col-xs-6 col-md-3">' + 
                              '<div class="thumbnail" id="' + img_id + '">' +
                              '<div class="caption">' +
                              '<input class="img-checkbox" name="' + img_id + '" type="checkbox">' +
                              '</div>' + 
                              '</div>' + 
                              '</div>');
    //place image in thumbnail
    $('#' + img_id).append(img);
  };

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

  /* Adds the signed hmac key to an array
   * that is sent back to the server for deletion   
   */
  $(document).on( "click", "input.img-checkbox", function() {

    var fname = $(this).attr("name");
    var is_checked = $(this).prop("checked");

    //checkbox is clicked, save filename in an array
    if(is_checked){

      selected_imgs.push(fname);
      console.log(selected_imgs);
    }
    //checkbox is unclicked, remove filename from the array
    else {

      var index = selected_imgs.indexOf(fname); 
      selected_imgs.splice(index, 1);
    }
  });

  ws.onmessage = function (evt) {
    var msg = JSON.parse(evt.data);
    //console.log(msg); //added

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

      case "image": //added
        update_results(msg.msg_id, msg.img_id, msg.enc_img, msg.signed_req);

      case "downloading":
        feedback(msg);
      update_progress(msg.num, num_messages);
      break;

      case "download-complete":
        feedback(msg, "Please check all attachments you'd like removed from your GMail account");
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
