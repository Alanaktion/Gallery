<?php
	/*
	*	Gallery 0.4 by Alan Hardman
	*	A tiny drop-in photo gallery with desktop and mobile support
	*/

	///////////////////
	// Configuration //
	///////////////////
	
	$newtab = false; // open images in a new tab when clicked.
	$dir   = '.';    // the directory to get images from, use '.' for the current directory.
	$size  = 150;    // thumbnail width/height in pixels.  150 is recommended for best display, mobile is always 75px.
	$cache = 30*24;  // time to cache images in hours (using cache header, nothing is cached on the server)
	$save  = true;   // save the generated thumbnails to prevent them from generating again on every page load
	$cmpct = false;  // keep thumbnails compacted into a single file (may be slow with large numbers of photos)
	                    // this feature is not yet working as expected!
	$sort  = true;   // sort files by name (otherwise they are ordered by the filesystem)
	$types = array(  // file types to attempt to open as images
		'jpg',
		'jpeg',
		'jpe',
		'png',
		'gif',
		'bmp'
	);
	$files  = false; // list non-image files
	$ftypes = array( // file types to list after images, leave empty to display all non-image files
		'txt',
		'zip',
		'rar'
	);
	
	$debug = true;  // Enable debug logging
	
	////////////////
	// Thumbnails //
	////////////////
	
	// If request is for a thumbnail, generate it
	if($_GET['t']) {
		
		// output cache headers
		$expires = 3600*$cache;
		header("Pragma: public");
		header("Cache-Control: maxage=".$expires);
		header('Expires: '.gmdate('D, d M Y H:i:s',time()+$expires).' GMT');
		
		// Content type
		header('Content-Type: image/jpeg');
		
		if($cmpct && $save) {
			// Compact thumbnail cache enabled
			
			// Get existing thumbnails
			if(is_file($dir.'/gallery.thm')) {
				$f = file_get_contents($dir.'/gallery.thm') or die('Unable to open cache file');
				$d = unserialize($f);
				
				// If requested thumbnail exists, output it
				if($d[$_GET['t']]) {
					if($debug)
						file_put_contents($dir.'/cacheread.log',$_GET['t']."\n",FILE_APPEND);
					print gzinflate($d[$_GET['t']]);
					exit();
				}
			} else
				$d = array();
			
			// Generate requested thumbnail
			mkthumb($_GET['t'],false);
			
			// Load generated thumbnail
			$t = file_get_contents($dir.'/zz_thm_'.$_GET['t'].'.tmp') or die('Unable to load temporary thumbnail');
			
			// Add thumbnail to the cache file
			$d[$_GET['t']] = gzdeflate($t);
			file_put_contents($dir.'/gallery.thm',serialize($d)) or die('Unable to save cache file');
			if($debug)
				file_put_contents($dir.'/generate.log',$_GET['t']."\n",FILE_APPEND);
			
			// Delete temp file and output thumbnail
			unlink($dir.'/zz_thm_'.$_GET['t'].'.tmp');
			print $t;
			
		} elseif(is_file($dir.'/zz_thm_'.$_GET['t'].'.tmp') && $save) {
			// Individual thumbnail file exists
			readfile($dir.'/zz_thm_'.$_GET['t'].'.tmp');
		} else {
			// No thumbnail cache exists, not using compact cache
			mkthumb($_GET['t']);
		}
		exit();
	}
	
	function mkthumb($src,$output = true) {
		global $save,$size,$dir;
		$img = @imagecreatefromstring(file_get_contents($dir.'/'.$src)); // load image file
		$res = imagecreatetruecolor($size,$size);  // create empty canvas for thumbnail
		$w = imagecolorallocate($res,255,255,255); // allocate white background color
		imagefill($res,0,0,$w);                    // fill image with white
		
		// get smaller of image's dimensions
		$d = (imagesx($img)>imagesy($img)) ? imagesy($img) : imagesx($img);
		
		// crop, resize, and copy from source image
		imagecopyresampled($res,$img,0,0,(imagesx($img)-$d)/2,(imagesy($img)-$d)/2,$size,$size,$d,$d);
		
		// output generated image
		if($save) {
			imagejpeg($res,$dir.'/zz_thm_'.$_GET['t'].'.tmp');
			if($output)
				readfile($dir.'/zz_thm_'.$_GET['t'].'.tmp');
		} else
			imagejpeg($res);
	}
	
	/////////////
	// Gallery //
	/////////////
	
	// Get list of images
	$imgs = array();
	$h = @opendir($dir);
	while($f = @readdir($h))
		if(in_array(pathinfo($f,PATHINFO_EXTENSION),$types)) { // select files with desired $types
			$s = getimagesize($f); // get image information
			if($s[0] && $s[1])     // check if image is valid
				$imgs[] = $f;      // add image to list
		}
	closedir($h);
	
	if($sort)
		sort($imgs);
	
	// Get list of files if enabled
	if($files) {
		array_push($types,'tmp','thm');
		$fils = array();
		$h = @opendir($dir);
		while($f = @readdir($h))
			if(empty($ftypes) && $f!='.' && $f!='..') {
				if(!in_array(pathinfo($f,PATHINFO_EXTENSION),$types)) // do not include images
					$fils[] = $f; // add file to list
			} else {
				if(in_array(pathinfo($f,PATHINFO_EXTENSION),$ftypes)) // select files with desired $ftypes
					$fils[] = $f; // add file to list
			}
		closedir($h);
		
		if($sort)
			sort($fils);
	}

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
		max-width: 936px;
		margin: 0 auto;
	}
	a {
		display: block;
		color: inherit;
		float: left;
		margin: 1px;
		padding: 0;
		border: 1px solid grey;
	}
	p > a {
		display: inline;
		float: none;
		margin: auto;
		border: none;
		color: inherit;
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
	hr {
		height: 0;
		border: none;
		border-top: 1px solid #808895;
		margin: 10px 0;
		padding: 0;
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
	
	// Output file list
	if($fils) {
		echo '<hr>';
		foreach($fils as $f)
			echo '<p><a href="'.$dir.'/'.$f.'" target="'.($newtab ? '_blank' : '_self').'">'.$f.'</a>';
	}
?>
</body>
</html>