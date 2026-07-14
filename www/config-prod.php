<?php

require_once('/srv/www/bbsengine6/php/bootstrap.php');
require_once('util.php');
\bbsengine6\util\add_include_paths([
    '/srv/www/vhosts/zoidtechnologies.com/html/casino/',
    '/srv/www/zoid6/php/',
    '/srv/www/bbsengine6/php/',
    '/srv/www/smarty/'
]);

// Define configuration constants in config namespace (required by bbsengine6)
// Using backslash prefix makes them accessible via defined('\config\CONSTANT')
define("config\SITEURL", "https://zoidtechnologies.com/casino/");
define("config\VHOSTDIR", "/srv/www/vhosts/zoidtechnologies.com/");
define("config\DOCUMENTROOT", \config\VHOSTDIR . "html/casino/");
define("config\SKINDIR", \config\DOCUMENTROOT . "skin/");
define("config\SKINURL", \config\SITEURL . "skin/");
define("config\JSURL", "/casino/skin/js/");
define("config\SITENAME", "casino");

// Define SMARTY* constants before including zoid6config.php so it can create global aliases
// SMARTYTEMPLATESDIR - 4-element array with proper precedence
// Search order: 1) Site-specific templates 2) zoid6 shared 3) zoid6 project 4) bbsengine6 shared
define("config\SMARTYTEMPLATESDIR", [
    0 => \config\SKINDIR . "tmpl/",
    1 => "/srv/www/vhosts/zoidtechnologies.com/html/shared/skin/tmpl/",
    2 => "/srv/www/vhosts/zoidtechnologies.com/html/shared/skin/tmpl/",
    3 => "/srv/www/bbsengine6/skin/tmpl/"
]);

// SMARTYCOMPILEDTEMPLATESDIR - compiled template cache directory
define("config\SMARTYCOMPILEDTEMPLATESDIR", \config\VHOSTDIR . "templates_c");

// SMARTYPLUGINSDIR - plugin directories for custom Smarty functions and modifiers
define("config\SMARTYPLUGINSDIR", [
    0 => \config\VHOSTDIR . "smarty/",
    1 => "/srv/www/zoid6/smarty/"
]);

// URL configuration for shared and engine resources
define("config\ENGINEURL", "/engine/");
define("config\ENGINESKINURL", "/engine/skin/");
define("config\SHAREDSKINURL", "/shared/skin/");

// Now include zoid6config.php to create global aliases
require_once('zoid6config.php');

define("config\LOGENTRYPREFIX", "zoid6casino");

// Create global aliases for non-SMARTY constants
// (SMARTY* aliases are created by zoid6config.php)
define("SITEURL", \config\SITEURL);
define("VHOSTDIR", \config\VHOSTDIR);
define("DOCUMENTROOT", \config\DOCUMENTROOT);
define("SKINDIR", \config\SKINDIR);
define("SKINURL", \config\SKINURL);
define("JSURL", \config\JSURL);
define("LOGENTRYPREFIX", \config\LOGENTRYPREFIX);

// Backward compatibility aliases for engine resources
define("ENGINEURL", \config\ENGINEURL);
define("ENGINESKINURL", \config\ENGINESKINURL);
define("SHAREDSKINURL", \config\SHAREDSKINURL);
define("STATICSKINURL", \config\SHAREDSKINURL);

?>
