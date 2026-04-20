<?php
/**
 * Gallery 0.6.3
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
		"7z",
		"heic",
		"heif",
		"svg",
	),

	"interface" => array(
		"dark" => "auto",
		"open_in_new_tab" => false,
		"labels" => true,
		"labels_only_on_hover" => true,
		"justified" => false,
	),

	"thumbnails" => array(
		"size" => 200,
		"cache" => true,
	)

);

if (function_exists('imagecreatefromavif')) {
	$config["image_extensions"][] = "avif";
}

// Check for AVIF and WebP thumbnail output support
$avif_encode_support = function_exists('imageavif');
$webp_encode_support = function_exists('imagewebp');

// Include user configuration file if it exists
if(is_file("gallery-config.php")) {
	include "gallery-config.php";
}



// Determine if we're on a Windows system
define("IS_WIN", (strncasecmp(PHP_OS, "WIN", 3) == 0) ? true : false);

/**
 * Normalize an untrusted relative path.
 * Returns null when traversal is attempted.
 */
function normalize_relative_path(?string $path): ?string
{
	if ($path === null) {
		return '';
	}

	$path = trim(str_replace("\0", '', $path));
	$path = str_replace('\\', '/', $path);
	$path = trim($path, '/');

	if ($path === '') {
		return '';
	}

	$segments = explode('/', $path);
	$normalized = array();
	foreach ($segments as $segment) {
		if ($segment === '' || $segment === '.') {
			continue;
		}
		if ($segment === '..') {
			return null;
		}
		$normalized[] = $segment;
	}

	return implode('/', $normalized);
}

/**
 * Resolve a relative path and ensure it stays within the configured base directory.
 */
function resolve_path_in_base(string $base_dir, ?string $relative_path, string $expected_type = 'any'): ?string
{
	$relative = normalize_relative_path($relative_path);
	if ($relative === null) {
		return null;
	}

	$base_dir = rtrim($base_dir, DIRECTORY_SEPARATOR);
	$candidate = $base_dir;
	if ($relative !== '') {
		$candidate .= DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relative);
	}

	$resolved = realpath($candidate);
	if ($resolved === false) {
		return null;
	}

	$base_prefix = $base_dir . DIRECTORY_SEPARATOR;
	if ($resolved !== $base_dir && strncmp($resolved, $base_prefix, strlen($base_prefix)) !== 0) {
		return null;
	}

	if ($expected_type === 'file' && !is_file($resolved)) {
		return null;
	}
	if ($expected_type === 'dir' && !is_dir($resolved)) {
		return null;
	}

	return $resolved;
}

/**
 * Build a stable thumbnail cache key from sanitized path parts.
 */
function build_thumb_cache_key(string $dir, string $name): string
{
	$dir = trim($dir, '/');
	return sha1($dir === '' ? $name : $dir . '/' . $name);
}

/**
 * Parse a request scale value and only allow integer values 1-3.
 */
function get_request_scale(array $request): int
{
	if (!isset($request['scale'])) {
		return 1;
	}

	$value = trim((string)$request['scale']);
	if (!preg_match('/^[1-3]$/', $value)) {
		return 1;
	}

	return (int)$value;
}

/**
 * Determine the thumbnail output format based on the request and server support.
 * Returns 'avif', 'webp', or 'jpeg'.
 */
function get_thumbnail_format(array $get, bool $avif_support, bool $webp_support): string
{
	$fmt = $get['fmt'] ?? '';
	if ($fmt === 'avif' && $avif_support) {
		return 'avif';
	}
	if ($webp_support) {
		return 'webp';
	}
	return 'jpeg';
}

/**
 * Output an image resource in the given format, optionally saving to a cache file.
 * $format must be one of: 'avif', 'webp', 'jpeg'.
 *
 * @param resource|\GdImage $res
 */
function output_thumbnail($res, string $format, string $cache_file = ''): void
{
	$content_types = ['avif' => 'image/avif', 'webp' => 'image/webp', 'jpeg' => 'image/jpeg'];
	$content_type = $content_types[$format] ?? 'image/jpeg';

	if ($cache_file !== '') {
		$encoded = false;
		if ($format === 'avif') {
			$encoded = imageavif($res, $cache_file);
		} elseif ($format === 'webp') {
			$encoded = imagewebp($res, $cache_file);
		} else {
			$encoded = imagejpeg($res, $cache_file);
		}
		if (!$encoded || !is_file($cache_file)) {
			header('HTTP/1.1 500 Internal Server Error');
			header('Content-Type: text/plain; charset=utf-8');
			echo 'Failed to generate thumbnail.';
			return;
		}
		header("Content-Type: " . $content_type);
		readfile($cache_file);
	} else {
		header("Content-Type: " . $content_type);
		if ($format === 'avif') {
			imageavif($res);
		} elseif ($format === 'webp') {
			imagewebp($res);
		} else {
			imagejpeg($res);
		}
	}
}

// Get the current filename for use in thumbnail, file, and folder links
$self = basename(__FILE__);

$base_dir_config = rtrim($config["directory"], "/\\");
$base_dir_real = realpath($base_dir_config);
if ($base_dir_real === false || !is_dir($base_dir_real)) {
	http_response_code(500);
	exit;
}

$config["base_directory"] = $base_dir_real;

// Get the requested gallery folder
$dir_level = 0;
$requested_dir = normalize_relative_path($_GET["dir"] ?? '');
$current_dir = '';
if ($requested_dir !== null && $requested_dir !== '') {
	$resolved_dir = resolve_path_in_base($config["base_directory"], $requested_dir, 'dir');
	if ($resolved_dir !== null) {
		$current_dir = $requested_dir;
		$dir_level = substr_count($current_dir, "/") + 1;
	}
}

$dir = rtrim($base_dir_config, "/\\");
if ($current_dir !== '') {
	$dir .= "/" . $current_dir;
}
$dir_fs = resolve_path_in_base($config["base_directory"], $current_dir, 'dir');



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
				@shell_exec('attrib +h ' . escapeshellarg($cache_dir));
			}
		}
	}

	// Output thumbnail
	$thm_name = normalize_relative_path($_GET["thm"] ?? '');
	if ($thm_name === null || $thm_name === '') {
		exit;
	}

	$file = build_thumb_cache_key($current_dir, $thm_name);
	if (!empty($config["interface"]["justified"])) {
		$file .= "-j";
	}
	$scale = get_request_scale($_GET);
	if ($scale > 1) {
		$file .= "@{$scale}x";
	}
	$thm_format = get_thumbnail_format($_GET, $avif_encode_support, $webp_encode_support);
	$thm_ext = ($thm_format === 'jpeg') ? 'jpg' : $thm_format;
	if($config["thumbnails"]["cache"] && is_file($cache_dir . "/" . $file . "." . $thm_ext)) {
		// Thumbnail cache exists, output it
		header("Content-Type: image/" . $thm_format);
		readfile($cache_dir . "/" . $file . "." . $thm_ext);
	} else {
		// No thumbnail cache exists, generate thumbnail
		$src = resolve_path_in_base($dir_fs, $thm_name, 'file');
		if($src !== null) {
			mkthumb($src, $config, $file, $scale, $thm_format);
		}
	}

	// All done.
	exit;
}

/**
 * Generate and optionally save a thumbnail image
 */
function mkthumb(string $src, array $config, string $file, int $scale = 1, string $format = 'jpeg')
{
	if ($scale < 1 || $scale > 3) {
		throw new Exception('Invalid thumbnail scale');
	}

	// Load image file, create canvas for new image, and fill it with gray
	$img = @imagecreatefromstring(file_get_contents($src));
	if(!$img) {
		return false;
	}

	$size = $config["thumbnails"]["size"] * $scale;
	$source_width = imagesx($img);
	$source_height = imagesy($img);
	$justified = !empty($config["interface"]["justified"]);
	if ($justified && $source_height > 0) {
		$target_height = $size;
		$target_width = max(1, (int) round($source_width * ($target_height / $source_height)));
		$res = imagecreatetruecolor($target_width, $target_height);
		$w = imagecolorallocate($res, 64, 64, 64);
		imagefill($res, 0, 0, $w);
		imagecopyresampled(
			$res, $img,
			0, 0,
			0, 0,
			$target_width, $target_height,
			$source_width, $source_height
		);
	} else {
		$res = imagecreatetruecolor($size, $size);
		$w = imagecolorallocate($res, 64, 64, 64);
		imagefill($res, 0, 0, $w);

		// Get smaller of image's dimensions
		$d = ($source_width > $source_height) ? $source_height : $source_width;

		// Crop, resize, and copy from source image
		imagecopyresampled(
			$res, $img,
			0, 0,
			($source_width - $d) / 2, ($source_height - $d) / 2,
			$size, $size,
			$d, $d
		);
	}

	// Save/output generated image
	$ext = ($format === 'jpeg') ? 'jpg' : $format;
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		output_thumbnail($res, $format, $cache_dir . "/" . $file . "." . $ext);
	} else {
		output_thumbnail($res, $format);
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
				@shell_exec('attrib +h ' . escapeshellarg($cache_dir));
			}
		}
	}

	// Output thumbnail
	$dirthm_name = normalize_relative_path($_GET["dirthm"] ?? '');
	if ($dirthm_name === null || $dirthm_name === '') {
		exit;
	}

	$file = build_thumb_cache_key($current_dir, $dirthm_name);
	$scale = get_request_scale($_GET);
	if ($scale > 1) {
		$file .= "@{$scale}x";
	}
	$thm_format = get_thumbnail_format($_GET, $avif_encode_support, $webp_encode_support);
	$thm_ext = ($thm_format === 'jpeg') ? 'jpg' : $thm_format;
	if($config["thumbnails"]["cache"] && is_file($cache_dir . "/" . $file . "." . $thm_ext)) {
		// Thumbnail cache exists, output it
		header("Content-Type: image/" . $thm_format);
		readfile($cache_dir . "/" . $file . "." . $thm_ext);
	} else {
		// No thumbnail cache exists, generate thumbnail
		$src = resolve_path_in_base($dir_fs, $dirthm_name, 'dir');
		if($src !== null) {
			mkdirthumb($src, $config, $file, $scale, $thm_format);
		}
	}

	// All done.
	exit;
}

/**
 * Generate and optionally save a thumbnail image
 */
function mkdirthumb($src, array $config, string $file, int $scale, string $format = 'jpeg')
{
	if ($scale < 1 || $scale > 3) {
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
	$ext = ($format === 'jpeg') ? 'jpg' : $format;
	if($config["thumbnails"]["cache"]) {
		$cache_dir = $config["base_directory"] . "/" . (IS_WIN ? "thm" : ".thm");
		output_thumbnail($res, $format, $cache_dir . "/" . $file . "." . $ext);
	} else {
		output_thumbnail($res, $format);
	}
}



// Scan folder for images and files
$directories = array();
$images = array();
$files = array();
$dh = opendir($dir_fs);
while(($f = readdir($dh)) !== false) {

	// Check if we're including directories and if the current item is a directory
	if($config["include_subdirectories"] && is_dir($dir_fs . "/" . $f) && substr($f, 0, 1) != "." && $f != 'thm') {
		$directories[] = $f;
	}

	// Check if file matches the image file extensions
	if(in_array(strtolower(pathinfo($dir_fs . "/" . $f, PATHINFO_EXTENSION)), $config["image_extensions"])) {
		// Attempt to get image metadata, and add it if successful
		$s = getimagesize($dir_fs . "/" . $f);
		if($s[0] && $s[1]) {
			$images[] = $f;
		}
	}

	// Check if file matches the generic file extensions
	if(!empty($config["file_extensions"]) && in_array(strtolower(pathinfo($dir_fs . "/" . $f, PATHINFO_EXTENSION)), $config["file_extensions"])) {
		$files[] = $f;
	}

}
closedir($dh);

// Remove hidden items on Windows
if(IS_WIN) {
	exec("DIR " . escapeshellarg($dir_fs) . " /AH /B", $hidden);
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
$justified = !empty($config["interface"]["justified"]);

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
	a picture {
		display: contents;
	}
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
	<?php if ($justified) { ?>
		.container {
			max-width: none !important;
		}
		.grid.justified-gallery {
			display: block !important;
		}
		.grid.justified-gallery a.image {
			float: none;
			margin: 0;
		}
	<?php } ?>

	/* Grid breakpoints */
<?php $c = 3; ?>
<?php while(($config["thumbnails"]["size"] + 6) * $c++ <= 3840) { ?>
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
		.grid.justified-gallery {
			display: block !important;
		}
		.grid.justified-gallery a.image {
			width: auto;
			aspect-ratio: auto;
		}
	}
</style>
<?php if (!empty($config["interface"]["dark"])): ?>
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
		background-color: #222;
	}
	a.dir:hover, a.dir:focus, a.image:hover, a.image:focus, a.file:hover, a.file:focus {
		outline-color: #444;
	}
	a.dir:focus, a.dir:hover {
		background-color: #333;
	}
<?php if ($config["interface"]["dark"] === 'auto'): ?>
}
<?php endif; ?>
</style>
<?php endif; ?>
<?php if ($justified) { ?>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/justifiedGallery@3.8.1/dist/css/justifiedGallery.min.css">
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/justifiedGallery@3.8.1/dist/js/jquery.justifiedGallery.min.js"></script>
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
			</p>
		<?php } ?>

		<?php $layout_qs = $justified ? '&amp;layout=j' : ''; ?>
		<?php if (!$justified) { ?>
			<div class="grid">
				<?php foreach($directories as $d) { ?>
					<a class="dir" href="<?= e($self) ?>?dir=<?= u($current_dir . "/" . $d) ?>" title="<?= e($d) ?>">
						<?php $dirthm_base = e($self) . "?dir=" . u($current_dir) . "&amp;dirthm=" . u($d); ?>
						<picture>
							<?php if($avif_encode_support): ?>
							<source srcset="<?= $dirthm_base ?>&amp;fmt=avif<?= $layout_qs ?> 1x, <?= $dirthm_base ?>&amp;fmt=avif&amp;scale=2<?= $layout_qs ?> 2x" type="image/avif">
							<?php endif; ?>
							<img src="<?= $dirthm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?><?= $layout_qs ?>"
								srcset="<?= $dirthm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?>&amp;scale=2<?= $layout_qs ?> 2x"
								loading="lazy" decoding="async"
								width="<?= $config['thumbnails']['size'] ?>"
								height="<?= $config['thumbnails']['size'] ?>">
						</picture>
						<span><?= e($d) ?></span>
					</a>
				<?php } ?>

				<?php foreach($images as $i) { ?>
					<a class="image" href="<?= e(rawurlencode($dir)) . "/" . e(rawurlencode($i)) ?>" title="<?= e($i) ?>" target="<?php if(!empty($config['interface']['open_in_new_tab'])) echo '_blank'; ?>">
						<?php $thm_base = e($self) . "?dir=" . u($current_dir) . "&amp;thm=" . u($i); ?>
						<picture>
							<?php if($avif_encode_support): ?>
							<source srcset="<?= $thm_base ?>&amp;fmt=avif<?= $layout_qs ?> 1x, <?= $thm_base ?>&amp;fmt=avif&amp;scale=2<?= $layout_qs ?> 2x" type="image/avif">
							<?php endif; ?>
							<img src="<?= $thm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?><?= $layout_qs ?>"
								srcset="<?= $thm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?>&amp;scale=2<?= $layout_qs ?> 2x"
								loading="lazy" decoding="async"
								width="<?= $config['thumbnails']['size'] ?>"
								height="<?= $config['thumbnails']['size'] ?>">
						</picture>
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
		<?php } else { ?>
			<?php if (count($directories) > 0) { ?>
				<div class="grid">
					<?php foreach($directories as $d) { ?>
						<a class="dir" href="<?= e($self) ?>?dir=<?= u($current_dir . "/" . $d) ?>" title="<?= e($d) ?>">
							<?php $dirthm_base = e($self) . "?dir=" . u($current_dir) . "&amp;dirthm=" . u($d); ?>
							<picture>
								<?php if($avif_encode_support): ?>
								<source srcset="<?= $dirthm_base ?>&amp;fmt=avif<?= $layout_qs ?> 1x, <?= $dirthm_base ?>&amp;fmt=avif&amp;scale=2<?= $layout_qs ?> 2x" type="image/avif">
								<?php endif; ?>
								<img src="<?= $dirthm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?><?= $layout_qs ?>"
									srcset="<?= $dirthm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?>&amp;scale=2<?= $layout_qs ?> 2x"
									loading="lazy" decoding="async"
									width="<?= $config['thumbnails']['size'] ?>"
									height="<?= $config['thumbnails']['size'] ?>">
							</picture>
							<span><?= e($d) ?></span>
						</a>
					<?php } ?>
				</div>
			<?php } ?>

			<div id="justified-grid" class="grid justified-gallery">
				<?php foreach($images as $i) { ?>
					<a class="image" href="<?= e(rawurlencode($dir)) . "/" . e(rawurlencode($i)) ?>" title="<?= e($i) ?>" target="<?php if(!empty($config['interface']['open_in_new_tab'])) echo '_blank'; ?>">
						<?php $thm_base = e($self) . "?dir=" . u($current_dir) . "&amp;thm=" . u($i); ?>
						<picture>
							<?php if($avif_encode_support): ?>
							<source srcset="<?= $thm_base ?>&amp;fmt=avif<?= $layout_qs ?> 1x, <?= $thm_base ?>&amp;fmt=avif&amp;scale=2<?= $layout_qs ?> 2x" type="image/avif">
							<?php endif; ?>
							<img src="<?= $thm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?><?= $layout_qs ?>"
								srcset="<?= $thm_base ?><?= $webp_encode_support ? '&amp;fmt=webp' : '' ?>&amp;scale=2<?= $layout_qs ?> 2x"
								loading="lazy" decoding="async"
								height="<?= $config['thumbnails']['size'] ?>">
						</picture>
						<?php if($config["interface"]["labels"]) { ?>
							<span><?= e($i) ?></span>
						<?php } ?>
					</a>
				<?php } ?>
			</div>

			<?php if (count($files) > 0) { ?>
				<div class="grid">
					<?php foreach($files as $f) { ?>
						<a class="file" href="<?= e(rawurlencode($dir)) . "/" . e(rawurlencode($f)) ?>" title="<?= e($f) ?>" target="<?php if(!empty($config['interface']['open_in_new_tab'])) echo '_blank'; ?>">
							<span><?= e($f) ?></span>
						</a>
					<?php } ?>
				</div>
			<?php } ?>
		<?php } ?>

		<div class="clear"></div>
		<?php if ($justified) { ?>
		<script>
		jQuery(function($) {
			$('#justified-grid').justifiedGallery({
				rowHeight: <?= (int) $config['thumbnails']['size'] ?>,
				margins: 4,
				lastRow: 'nojustify'
			});
		});
		</script>
		<?php } ?>
		<footer><?php echo count($directories) + count($images) + count($files); ?> items</footer>
	</div>
</body>
</html>
