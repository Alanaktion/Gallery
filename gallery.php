<?php
/**
 * Gallery 0.6.2
 * The ultimate single-file photo gallery
 * @author Alan Hardman <alan@phpizza.com>
 */

/**
 * Default configuration
 *
 * In order to make updates easier, it's recommended to include changes to
 * configuration in a separate file named gallery-config.php. This file will
 * be automatically included if it exists, and can be used to override either
 * individual configuration options or the entire $config array.
 *
 * Note: after changing thumbnail size, you will need to remove the existing
 * cached thumbnail files from the hidden thm directory.
 */
$config = array(

	"title" => "Gallery",
	"directory_title" => true, // Prepend subdirectory name to page title

	"directory" => "./", // Must include trailing slash

	"include_subdirectories" => true,

	"image_extensions" => array(
		"jpg",
		"jpeg",
		"jpe",
		"jfif",
		"png",
		"gif",
		"bmp",
		"webp",
	),

	"file_extensions" => array(
		"txt",
		"zip",
		"rar",
	),

	"interface" => array(
		"dark" => "auto",
		"open_in_new_tab" => false,
		"labels" => true,
		"labels_only_on_hover" => true,
	),

	"thumbnails" => array(
		"size" => 200,
		"cache" => true,
	)

);

// Include user configuration file if it exists
if(is_file("gallery-config.php")) {
	include "gallery-config.php";
}



// Determine if we're on a Windows system
define("IS_WIN", (strncasecmp(PHP_OS, "WIN", 3) == 0) ? true : false);

// Get the current filename for use in thumbnail, file, and folder links
$self = basename(__FILE__);

// Get the requested gallery folder
$dir_level = 0;
$config["base_directory"] = $config["directory"];
if(!empty($_GET["dir"])) {
	$_GET["dir"] = trim($_GET["dir"], "/");
	if(strpos($_GET["dir"], "../") === false && is_dir($config["directory"] . $_GET["dir"])) {
		$config["directory"] .= $_GET["dir"];
		$dir_level = substr_count($_GET["dir"], "/") + 1;
	}
}

$dir = rtrim($config["directory"], "/");
$current_dir = ltrim($dir, "./");



// Handle thumbnail generation requests
if(!empty($_GET["thm"])) {

	// Send client-side caching headers
	$expires = 3600 * 30 * 24;
	header("Pragma: public");
	header("Cache-Control: maxage=" . $expires);
	header("Expires: " . gmdate("D, d M Y H:i:s", time() + $expires) . " GMT");

	// Determine thumbnail cache directory
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		if(!is_dir($cache_dir)) {
			mkdir($cache_dir);
			if(IS_WIN) {
				// Hide folder on Windows
				@shell_exec("attrib +h {$cache_dir}");
			}
		}
	}

	// Output thumbnail
	$file = empty($_GET["dir"]) ? sha1($_GET["thm"]) : sha1($_GET["dir"] . $_GET["thm"]);
	$scale = (int)($_GET['scale'] ?? 1);
	if ($scale > 1) {
		$file .= "@{$scale}x";
	}
	if($config["thumbnails"]["cache"] && is_file($cache_dir . "/" . $file . ".jpg")) {
		// Thumbnail cache exists, output it
		header("Content-Type: image/jpeg");
		readfile($cache_dir . "/" . $file . ".jpg");
	} else {
		// No thumbnail cache exists, generate thumbnail
		if(strpos($_GET["thm"], "../") === false && is_file($dir . "/" . $_GET["thm"])) {
			$src = $dir . "/" . $_GET["thm"];
			mkthumb($src, $config, $scale);
		}
	}

	// All done.
	exit;
}

/**
 * Generate and optionally save a thumbnail image
 */
function mkthumb(string $src, array $config, int $scale = 1)
{
	if ($scale > 3) {
		throw new Exception('Invalid thumbnail scale');
	}

	// Load image file, create canvas for new image, and fill it with gray
	$img = @imagecreatefromstring(file_get_contents($config["base_directory"] . "/" . $src));
	if(!$img) {
		return false;
	}

	$size = $config["thumbnails"]["size"] * $scale;
	$res = imagecreatetruecolor($size, $size);
	$w = imagecolorallocate($res, 64, 64, 64);
	imagefill($res, 0, 0, $w);

	// Get smaller of image's dimensions
	$d = (imagesx($img) > imagesy($img)) ? imagesy($img) : imagesx($img);

	// Crop, resize, and copy from source image
	imagecopyresampled(
		$res, $img,
		0, 0,
		(imagesx($img) - $d) / 2, (imagesy($img) - $d) / 2,
		$size, $size,
		$d, $d
	);


	// Save/output generated image
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		$file = empty($_GET["dir"]) ? sha1($_GET["thm"]) : sha1($_GET["dir"] . $_GET["thm"]);
		if ($scale > 1) {
			$file .= "@{$scale}x";
		}
		imagejpeg($res, $cache_dir . "/" . $file . ".jpg");

		header("Content-Type: image/jpeg");
		readfile($cache_dir . "/" . $file . ".jpg");
	} else {
		header("Content-Type: image/jpeg");
		imagejpeg($res);
	}
}



// Handle directory thumbnails
if(!empty($_GET["dirthm"])) {

	// Send client-side caching headers
	$expires = 3600 * 30 * 24;
	header("Pragma: public");
	header("Cache-Control: maxage=" . $expires);
	header("Expires: " . gmdate("D, d M Y H:i:s", time() + $expires) . " GMT");

	// Determine thumbnail cache directory
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		if(!is_dir($cache_dir)) {
			mkdir($cache_dir);
			if(IS_WIN) {
				// Hide folder on Windows
				@shell_exec("attrib +h {$cache_dir}");
			}
		}
	}

	// Output thumbnail
	$file = sha1($dir . "/" . $_GET["dirthm"]);
	$scale = (int)($_GET['scale'] ?? 1);
	if ($scale > 1) {
		$file .= "@{$scale}x";
	}
	if($config["thumbnails"]["cache"] && is_file($cache_dir . "/" . $file . ".jpg")) {
		// Thumbnail cache exists, output it
		header("Content-Type: image/jpeg");
		readfile($cache_dir . "/" . $file . ".jpg");
	} else {
		// No thumbnail cache exists, generate thumbnail
		if(strpos($_GET["dirthm"], "../") === false && is_dir($dir . "/" . $_GET["dirthm"])) {
			$src = $dir . "/" . $_GET["dirthm"];
			mkdirthumb($src, $config, $scale);
		}
	}

	// All done.
	exit;
}

/**
 * Generate and optionally save a thumbnail image
 */
function mkdirthumb($src, array $config, int $scale)
{
	if ($scale > 3) {
		throw new Exception('Invalid thumbnail scale');
	}

	// Find up to 4 image files in directory
	$images = array();
	$dh = opendir($src);
	while(($f = readdir($dh)) !== false && count($images) < 4) {
		// Check if file matches the image file extensions
		if(in_array(strtolower(pathinfo($src . "/" . $f, PATHINFO_EXTENSION)), $config["image_extensions"])) {
			// Attempt to get image metadata, and add it if successful
			$s = getimagesize($src . "/" . $f);
			if($s[0] && $s[1]) {
				$images[] = $f;
			}
		}
	}
	closedir($dh);

	// Create canvas for new image, and fill it with gray
	$size = $config["thumbnails"]["size"];
	$res = imagecreatetruecolor($size, $size);
	$w = imagecolorallocate($res, 64, 64, 64);
	imagefill($res, 0, 0, $w);

	// Add images to thumbnail
	$i = 0;
	foreach($images as $f) {
		$img = imagecreatefromstring(file_get_contents($src . "/" . $f));

		// Get smaller of image's dimensions
		$d = (imagesx($img) > imagesy($img)) ? imagesy($img) : imagesx($img);

		// Crop, resize, and copy from source image
		imagecopyresampled(
			$res, $img,
			($i % 2) * $size / 2, intval($i >= 2) * $size / 2,
			(imagesx($img) - $d) / 2, (imagesy($img) - $d) / 2,
			$size / 2, $size / 2,
			$d, $d
		);

		$i++;
	}

	// Save/output generated image
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		$file = sha1($src);
		if ($scale > 1) {
			$file .= "@{$scale}x";
		}
		imagejpeg($res, $cache_dir . "/" . $file . ".jpg");

		header("Content-Type: image/jpeg");
		readfile($cache_dir . "/" . $file . ".jpg");
	} else {
		header("Content-Type: image/jpeg");
		imagejpeg($res);
	}
}



// Scan folder for images and files
$directories = array();
$images = array();
$files = array();
$dh = opendir($dir);
while(($f = readdir($dh)) !== false) {

	// Check if we're including directories and if the current item is a directory
	if($config["include_subdirectories"] && is_dir($dir . "/" . $f) && substr($f, 0, 1) != "." && $f != 'thm') {
		$directories[] = $f;
	}

	// Check if file matches the image file extensions
	if(in_array(strtolower(pathinfo($dir . "/" . $f, PATHINFO_EXTENSION)), $config["image_extensions"])) {
		// Attempt to get image metadata, and add it if successful
		$s = getimagesize($dir . "/" . $f);
		if($s[0] && $s[1]) {
			$images[] = $f;
		}
	}

	// Check if file matches the generic file extensions
	if(!empty($config["file_extensions"]) && in_array(strtolower(pathinfo($dir . "/" . $f, PATHINFO_EXTENSION)), $config["file_extensions"])) {
		$files[] = $f;
	}

}
closedir($dh);

// Remove hidden items on Windows
if(IS_WIN) {
	exec("DIR \"{$dir}\" /AH /B", $hidden);
	foreach($hidden as $item) {
		if($key = array_search(trim($item), $directories)) {
			unset($directories[$key]);
		}
		if($key = array_search(trim($item), $images)) {
			unset($images[$key]);
		}
		if($key = array_search(trim($item), $files)) {
			unset($files[$key]);
		}
	}
}

function e($str) {
	return htmlspecialchars($str, ENT_QUOTES);
}
function u($str) {
	return e(urlencode($str));
}

natsort($images);
natsort($files);

$title = $config["title"];
if ($current_dir) {
	$title = basename($dir) . " - " . $config["title"];
}

?>
<!doctype html>
<html>
<head>
	<meta charset="utf-8">
	<title><?php echo $title; ?></title>
	<meta name="viewport" content="width=device-width,maximum-scale=1">
	<style type="text/css">
	html, body {
		height: 100%;
		margin: 0;
		padding: 0;
	}
	body {
		font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
		font-size: 14px;
		line-height: 1.42857;
		color: #333;
		background-color: #FFF;
	}
	.container {
		margin: 0 auto;
		padding: 2px 0;
	}

	.breadcrumbs {
		padding: 0 15px;
		font-size: 16px;
	}
	.breadcrumbs a {
		color: #428BCA;
		text-decoration: none;
	}
	.breadcrumbs a:hover,
	.breadcrumbs a:focus {
		color: #2A6496;
		text-decoration: underline;
	}

	a.dir,
	a.image,
	a.file {
		position: relative;
		display: block;
		width: <?php echo $config["thumbnails"]["size"]; ?>px;
		height: <?php echo $config["thumbnails"]["size"]; ?>px;
		border: 1px solid #fff;
		outline: 1px solid #777;
		margin: 2px;
		float: left;
		text-decoration: none;
	}
	a.dir:after,
	a.image:after,
	a.file:after {
		content: '';
		position: absolute;
		top: 0;
		right: 0;
		bottom: 0;
		left: 0;
		box-shadow: 1px 1px 0 rgba(255, 255, 255, 0.2) inset,
					-1px -1px 0 rgba(255, 255, 255, 0.2) inset;
	}
	a.dir {background-color: #eee;}
	a.dir:hover, a.dir:focus {background-color: #f5f5f5;}
	a.image {background-color: #fff;}
	a.file {
		background-color: #444;
		background-image: url('data:image/svg+xml;utf8,%3C%3Fxml%20version%3D%221.0%22%20encoding%3D%22UTF-8%22%20standalone%3D%22no%22%20%3F%3E%3Csvg%20width%3D%2264px%22%20height%3D%2278px%22%20viewBox%3D%220%200%2064%2078%22%20version%3D%221.1%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20xmlns%3Axlink%3D%22http%3A%2F%2Fwww.w3.org%2F1999%2Fxlink%22%3E%3Cg%20stroke%3D%22none%22%20stroke-width%3D%221%22%20fill%3D%22none%22%20fill-rule%3D%22evenodd%22%3E%3Cpath%20d%3D%22M20%2C0%20L0%2C20%20L0%2C78%20L64%2C78%20L64%2C0%20L20%2C0%20Z%22%20fill%3D%22%23D5D5D5%22%3E%3C%2Fpath%3E%3Cpath%20d%3D%22M0.166992188%2C20.0644531%20L20%2C20.0644531%20L20%2C0%20L0.166992188%2C20.0644531%20Z%22%20fill%3D%22%23F5F5F5%22%3E%3C%2Fpath%3E%3C%2Fg%3E%3C%2Fsvg%3E');
		background-position: center center;
		background-repeat: no-repeat;
	}
	a.file:hover, a.file:focus {background-color: #4c4c4c;}
	a img {
		display: block;
		max-width: 100%;
		height: auto;
		transition: filter 0.2s ease;
	}
	a:hover img,
	a:focus img {
		filter: brightness(1.1);
	}
	a span {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: 5px;
		text-align: center;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		background: rgba(0, 0, 0, .5);
		color: #fff;
		-webkit-backdrop-filter: blur(30px);
		backdrop-filter: blur(30px);
	}
	<?php if($config["interface"]["labels_only_on_hover"]) { ?>
		a.image span {
			opacity: 0;
			transition: opacity 0.2s ease;
		}
		a.image:hover span,
		a.image:focus span {
			opacity: 1;
		}
	<?php } ?>

	footer {
		padding: 10px;
		font-size: 16px;
		text-align: center;
		color: #777;
	}
	.clear {clear: both;}

	/* Grid breakpoints */
<?php $c = 3; ?>
<?php while(($config["thumbnails"]["size"] + 6) * $c++ < 3400) { ?>
	@media only screen and (min-width: <?php echo ($config["thumbnails"]["size"] + 6) * $c; ?>px) {
		.container{
			max-width: <?php echo ($config["thumbnails"]["size"] + 6) * $c; ?>px;
		}
	}
<?php } ?>
	@media only screen and (max-width: <?php echo ($config["thumbnails"]["size"] + 6) * 4; ?>px) {
		.container {
			max-width: none !important;
		}
		.grid {
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(<?php echo ($config["thumbnails"]["size"] / 2) + 6; ?>px, 1fr));
			gap: 2px;
		}
		a.dir,
		a.image,
		a.file {
			float: none;
			width: 100%;
			height: auto;
			aspect-ratio: 1/1;
			margin: 0;
			border: none;
			outline: none;
		}
		a.file {
			background-size: 32px 39px;
		}
	}
</style>
<?php if(@$config["interface"]["dark"]) { ?>
<style type="text/css">
<?php if ($config["interface"]["dark"] === 'auto'): ?>
@media only screen and (prefers-color-scheme: dark) {
<?php endif; ?>
	body {
		background: #111;
		color: #ccc;
	}
	a.dir, a.image, a.file {
		border-color: #000;
		outline-color: #222;
	}
	a.dir:hover, a.dir:focus, a.image:hover, a.image:focus, a.file:hover, a.file:focus {
		outline-color: #444;
	}
<?php if ($config["interface"]["dark"] === 'auto'): ?>
}
<?php endif; ?>
</style>
<?php } ?>
</head>
<body>
	<div class="container">
		<?php if($dir_level) { ?>
			<p class="breadcrumbs"><a href="<?= e($self) ?>"><?= e($config["title"]) ?></a> /
				<?php
				$levels = explode("/", $current_dir);
				$i = 0;
				foreach($levels as $lvl) {
					$i++;
					$n = 0;
					$link_dir = $current_dir;
					while($n++ < $dir_level - $i) {
						$link_dir = dirname($link_dir);
					}
				?>
					<a href="<?= e($self) ?>?dir=<?= u($link_dir) ?>"><?= e($lvl) ?></a> /
				<?php
				}
				?>
			</a></p>
		<?php } ?>

		<div class="grid">
			<?php foreach($directories as $d) { ?>
				<a class="dir" href="<?= e($self) ?>?dir=<?= u($current_dir . "/" . $d) ?>" title="<?= e($d) ?>">
					<img src="<?= e($self) ?>?dir=<?= u($current_dir) ?>&amp;dirthm=<?= u($d) ?>"
						srcset="<?= e($self) ?>?dir=<?= u($current_dir) ?>&amp;dirthm=<?= u($d) ?>&amp;scale=2 2x"
						width="<?= $config['thumbnails']['size'] ?>"
						height="<?= $config['thumbnails']['size'] ?>">
					<span><?= e($d) ?></span>
				</a>
			<?php } ?>

			<?php foreach($images as $i) { ?>
				<a class="image" href="<?= e(rawurlencode($dir)) . "/" . e(rawurlencode($i)) ?>" title="<?= e($i) ?>" target="<?php if(!empty($config['interface']['open_in_new_tab'])) echo '_blank'; ?>">
					<img src="<?= e($self) ?>?dir=<?= u($current_dir) ?>&amp;thm=<?= u($i) ?>"
						srcset="<?= e($self) ?>?dir=<?= u($current_dir) ?>&amp;thm=<?= u($i) ?>&amp;scale=2 2x"
						width="<?= $config['thumbnails']['size'] ?>"
						height="<?= $config['thumbnails']['size'] ?>">
					<?php if($config["interface"]["labels"]) { ?>
						<span><?= e($i) ?></span>
					<?php } ?>
				</a>
			<?php } ?>

			<?php foreach($files as $f) { ?>
				<a class="file" href="<?= e(rawurlencode($dir)) . "/" . e(rawurlencode($f)) ?>" title="<?= e($f) ?>" target="<?php if(!empty($config['interface']['open_in_new_tab'])) echo '_blank'; ?>">
					<span><?= e($f) ?></span>
				</a>
			<?php } ?>
		</div>

		<div class="clear"></div>
		<footer><?php echo count($directories) + count($images) + count($files); ?> items</footer>
	</div>
</body>
</html>
