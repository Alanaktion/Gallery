<?php
	/*
	*	Gallery 0.1 by Alan Hardman
	*	A tiny drop-in photo gallery with desktop, mobile, and high-resolution support
	*/

	///////////////////
	// Configuration //
	///////////////////
	
	$newtab = false; // open images in a new tab when clicked.
	$dir = '.';      // the directory to get images from, use '.' for the current directory.
	$size = 150;     // thumbnail width/height in pixels.  150 is recommended for best display, mobile is always 75px.
	$cache = 30*24;  // time to cache images in hours (using cache header, nothing is cached on the server)
	$types = array(  // file types to attempt to open as images
		'jpg',
		'jpeg',
		'jpe',
		'png',
		'gif',
		'bmp'
	);
	
	
	// If request is for a thumbnail, generate it
	if($_GET['t']) {
		$img = imagecreatefromstring(file_get_contents($dir.'/'.$_GET['t'])); // load image file
		$res = imagecreatetruecolor($size,$size);  // create empty canvas for thumbnail
		$w = imagecolorallocate($res,255,255,255); // allocate white background color
		imagefill($res,0,0,$w);                    // fill image with white
		
		// get smaller of image's dimensions
		$d = (imagesx($img)>imagesy($img)) ? imagesy($img) : imagesx($img);
		
		// crop, resize, and copy from source image
		imagecopyresampled($res,$img,0,0,(imagesx($img)-$d)/2,(imagesy($img)-$d)/2,$size,$size,$d,$d);
		
		// output cache headers
		$expires = 3600*$cache;
		header("Pragma: public");
		header("Cache-Control: maxage=".$expires);
		header('Expires: '.gmdate('D, d M Y H:i:s',time()+$expires).' GMT');
		
		// output generated image
		header('Content-Type: image/jpeg');
		imagejpeg($res);
		exit();
	}
	
	
	// Get list of images
	$h = @opendir($dir);
	while($f = @readdir($h)) // vvv select files with desired $types
		if(in_array(pathinfo($f,PATHINFO_EXTENSION),$types)) {
			$s = getimagesize($f); // get image information
			if($s[0] && $s[1])     // check if image is valid
				$imgs[] = $f;      // add image to list
		}
	closedir($h);

?>
<!doctype html>
<html>
<head>
	<title>Gallery</title>
	<meta name="viewport" content="width=device-width,maximum-scale=1">
	<style type="text/css">
	body {
		margin: 0;
		padding: 2px;
		background: white;
	}
	div {
		margin: 0;
		padding: 0;
		max-width: 900px;
		margin: 0 auto;
	}
	a {
		display: block;
		float: left;
		margin: 1px;
		padding: 0;
		border: 1px solid grey;
	}
	img {
		display: block;
		border: none;
		margin: 0;
		padding: 1px;
		width: <?php echo $size; ?>px;
		height: <?php echo $size; ?>px;
	}
	p {
		display: block;
		clear: both;
		margin: 0;
		padding: 0;
		height: 45px;
		line-height: 45px;
		font-family: "Helvetica Neue", Arial, Helvetica, sans-serif;
		font-size: 20px;
		text-align: center;
		color: #808895;
	}
	
	@media only screen and (max-device-width: 480px),(max-device-width: 640px) {
		div {
			max-width: none;
		}
		a {
			margin: 2px;
			border: none;
		}
		img {
			padding: 0;
			width: 75px;
			height: 75px;
			-webkit-box-shadow: 0 0 2px rgba(0,0,0,.4) inset;
			-moz-box-shadow: 0 0 2px rgba(0,0,0,.4) inset;
			box-shadow: 0 0 2px rgba(0,0,0,.4) inset;
		}
	}
	</style>
</head>
<body>
<?php
	// Output image list
	echo '<div>';
	foreach($imgs as $i) {
		echo '<a href="'.$dir.'/'.$i.'" target="'.($newtab ? '_blank' : '_self').'">';
		echo '<img src="gallery.php?t='.urlencode($i).'" alt="'.$i.'">';
		echo '</a>';
	}
	echo '</div>';
	
	// Show number of pictures
	echo '<p>'.count($imgs).' Pictures</p>';
?>
</body>
</html>