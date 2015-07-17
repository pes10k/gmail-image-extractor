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
		$delete = $("#delete"),
		$select_all = $("#select-all"),
		select_bool = false,
		$image_menu = $("#image-menu"),
		$save = $("#save"),
		rewrite_index = null,
		rewrite_total = null,
		feedback = null,
		num_messages = null,
		update_progress = null,
		hide_progress = null,
		update_results = null, //added 
		img_id = null,
		hide_results = null, //added
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

		//create thumbnail for image to be displayed in
		//create a unique img_id for the purpose of selecting each image
		$results_container.append('<div class="col-xs-6 col-md-3">' + 
								  '<div class="thumbnail">' +
								  '<input class="img-checkbox" id="' + img_id + 
								  '" name="' + signed_req + '" type="checkbox">' +
								  '<img src="' + img.src + '">' +
								  '</div>' + 
								  '</div>');
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

	$select_all.click(function(){

		var img_id = [];

		//select all inputs if not selected
		if(select_bool === false){

			$("input.img-checkbox").prop("checked", true);	

			$("input.img-checkbox").each(function(){
				img_id.push([$(this).attr("name"), $(this).attr("id")]); 
			}); 

			select_bool = true;

			//push all selected images to selected images array
			selected_imgs.push(img_id);

			//change name of button to deselect all
			$("#select-all").text("Deselect All");

		}

		//deselect all inputs if selected
		else {

			$("input").prop("checked", false);	
			select_bool = false;

			//pop all selected images in selected images array
			selected_imgs = [];

			//change name of button to select all
			$("#select-all").text("Select All");
		}
		//change delete button state
		num_checked = count_checked();
		changeBtnState(num_checked, "delete");
		changeBtnState(num_checked, "save");
	});

	//on click sends selected images to server to retreive full sized images
	$save.click(function(){

		var params = {};

		//if not images are selected, display modal
		if (selected_imgs.length === 0) {

			$('#saveModal').modal('show');
		}
		//send all selected images to backend
		else {

			params = JSON.stringify({
				"type": "save",
				"images": selected_imgs	
			});

			ws.send(params);
		}

	});

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

	//sends currently selected images to the backend for removal
	$delete.click(function () {

		var params = JSON.stringify({
			"type" : "delete",
			"image" : selected_imgs
		});

		ws.send(params);

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

	var count_checked = function() {
		return $( "input:checked" ).length;
	};

	String.prototype.capitalizeFirstLetter = function(){
		return this.charAt(0).toUpperCase() + this.slice(1);
	};

	var changeBtnState = function(value, msg){

		msg = msg.toLowerCase();

		var $type = $( "#" + msg);

		msg = msg.capitalizeFirstLetter();

		if(value === 0){

			$type.addClass("disabled");
			$type.text(msg + " Image");
		}
		else if(value === 1){

			$type.removeClass("disabled");
			$type.text(msg + " Image");
		}
		else if(value > 1){

			$type.removeClass("disabled");
			$type.text(msg + " Images");
		}
		else{
			
			return; //an error has occured
		}
	};

	/* 
	 * Adds the signed hmac key to an array
	 */
	$(document).on( "click", "input.img-checkbox", function() {

		var img_id = [ $(this).attr("name"), $(this).attr("id") ];
		var is_checked = $(this).prop('checked');
		var num_checked = count_checked();

		changeBtnState(num_checked, "delete");
		changeBtnState(num_checked, "save");

		//checkbox is clicked, save filename in an array
		if(is_checked){

			selected_imgs.push(img_id);
		}
		//checkbox is unclicked, remove filename from the array
		else {

			var index = selected_imgs.indexOf(img_id); 
			selected_imgs.splice(index, 1);
		}
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

			case "image": //added
				$image_menu.fadeIn();
			update_results(msg.msg_id, msg.img_id, msg.enc_img, msg.hmac_key);

			case "downloading":
				feedback(msg);
			update_progress(msg.num, num_messages);
			break;

			case "download-complete":
				feedback(msg, "Please check all attachments you'd like removed from your GMail account");
			hide_progress();
			//$sync_form.fadeIn();
			break;

			case "file-checking":
				feedback(msg);
			update_progress();
			//$sync_form.fadeOut();
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
