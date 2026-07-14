<?php

require_once('/srv/www/bbsengine6/php/bootstrap.php');

require_once("config.php");

require_once("engine.php");
require_once("session.php");
require_once("database.php");

require_once("zoid6.php");

class index
{
  function main()
  {
    \bbsengine6\session\start();

    \bbsengine6\setcurrentsite(\config\SITENAME);
    \bbsengine6\setcurrentpage("index");
    \bbsengine6\setcurrentaction("index");
    \bbsengine6\setreturnto(SITEURL);

    $games = [
      [
        "name" => "Blackjack",
        "description" => "Hit, stand, split, double down, insurance, surrender. 3:2 blackjack payout, configurable dealer soft-17 rule, 5-card Charlie, spectator mode.",
      ],
      [
        "name" => "Poker",
        "description" => "Full hand evaluation, pot/side-pot calculation, showdown.",
        "variants" => [
          ["name" => "Texas Hold'em", "details" => "No-Limit, Pot-Limit, Fixed-Limit"],
          ["name" => "Omaha", "details" => "Pot-Limit, must use 2 hole cards + Omaha Hi-Lo"],
          ["name" => "7-Card Stud", "details" => "Fixed-Limit"],
        ],
      ],
      [
        "name" => "Slots",
        "description" => "5x3 reel slot machine, configurable RTP (default 92%), atomic bank transactions, paytable evaluation, statistics tracking.",
      ],
      [
        "name" => "Yahtzee",
        "description" => "Dice game with scoring categories, banker integration.",
      ],
      [
        "name" => "Tic-Tac-Toe",
        "description" => "AI-vs-AI spectator, human-vs-AI, human-vs-human networked. Alpha-beta minimax AI, bank/betting integration.",
      ],
    ];

    $data = [];
    $data["games"] = $games;
    $data["choices"] = \zoid6\buildchoices([]);
    \bbsengine6\displaypage($data, "index.tmpl");

    return;
  }
};

$a = new index();
$a->main();

?>
