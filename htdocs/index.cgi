#!/usr/bin/env perl

# qlhud.net
#
# Copyright 2013, Nico R. Wohlgemuth

use utf8;
use strict;
use warnings;

use feature 'switch';

use Time::HiRes qw(gettimeofday tv_interval);
my $begintime;
BEGIN { $begintime = [gettimeofday()]; }

use POSIX 'ceil';
use CGI ':standard';
use CGI::Carp 'fatalsToBrowser';
    CGI::Carp::set_message('Please report the bug to: qlhud@lifeisabug.com');
use CGI::Cookie;
use HTML::Entities;
use HTML::TagCloud;
use Template;
use DBI;
use File::Type;
use Imager;

$CGI::POST_MAX = 1024 * 1024 * 3;

my %vars = (
   defhudsperpage   => 6,
   defhudsrss       => 10,
   domain           => 'qlhud.net',
   maxhudsperpage   => 50,
   maxhudspersearch => 250,
   titleappend      => ' - QLHUD: Custom HUDs for Quake Live - Your QL custom HUD resource',
   url              => 'http://qlhud.net',
   huddir           => '/srv/www/qlhud.net/htdocs/files/huds',
   screenshotdir    => '/srv/www/qlhud.net/htdocs/files/screenshots',
   tempdir          => '/tmp/qlhud_temp',
);

my %ttopts = (
   INCLUDE_PATH => '/srv/www/qlhud.net/templates/',
   PRE_CHOMP    => 2,
   POST_CHOMP   => 2,
);

my %sql = (
   host      => '',
   db        => '',
   table     => 'huds',
   sesstable => 'sessions',
   user      => '',
   pass      => '',
   defhud    => 'id,uniqid,author,timestamp,description,imgy,clicks,downloads',
);

my %irc = (
   gate => '/usr/home/k/ircgate_nico/rizon',
   chan => '#/dev/null',
);

my $tt = Template->new(\%ttopts);
die("template folder $ttopts{INCLUDE_PATH} does not exist") unless (-e $ttopts{INCLUDE_PATH});

my $dbh;

my $ip   = $ENV{REMOTE_ADDR};
my $post = 1 if (request_method eq 'POST');

my $qauthor      = param('author');
my $qdescription = param('description');
my $qdest        = param('dest')  || 'index';
my $qexact       = param('exact');
my $qhud         = param('hud');
my $qnum         = param('num')   || $vars{defhudsperpage};
my $qpage        = param('page')  || 1;
my $qscreenshot  = param('screenshot');
my $qsort        = param('sort')  || 'id';
my $quniqid      = param('uniqid');

my %cookies = CGI::Cookie->fetch;

unless ($post) {
   if ($cookies{qlhud}) {
      my $cookie = $cookies{qlhud}->value;

      ($qnum, $qsort) = split(/\|/, $cookie);
   }
}

unless ($qnum =~ /^\d+$/) {
   $qnum = $vars{defhudsperpage};
}
elsif ($qnum > $vars{maxhudsperpage}) {
   $qnum = $vars{maxhudsperpage};
}

unless ($qpage =~ /^\d+$/) {
   $qpage = 1;
}

unless($qsort ~~ [qw(id downloads clicks)]) {
   $qsort = 'id';
}

my $cookie = CGI::Cookie->new(
   -name    => 'qlhud',
   -value   => $qnum . '|' . $qsort,
   -domain  => '.' . $vars{domain},
   -expires => '+7d',
);

mysql_connect() unless ($qdest eq 'about' || (!$post && $qdest eq 'upload'));

my $totalhuds = counthuds() if ($dbh);

given ($qdest) {
   when('about')    { page_about(); }
   when('authors')  { page_authors(); }
   when('download') { page_download(); }
   when('random')   { page_random(); }
   when('rss')      { page_rss(); }
   when('search')   { page_search(); }
   when('uniqid')   { page_uniqid(); }
   when('upload')   { $post ? page_upload_post() : page_upload(); }
   default          { page_index(); }
}

mysql_disconnect();

### functions

sub counthuds {
   my $result = $dbh->selectrow_arrayref("SELECT COUNT(*) as cnt FROM $sql{table}");

   return @$result[0];
}

sub irc {
   my $msg = shift;

   open my $ircgate, ">>", $irc{gate};
   print $ircgate $irc{chan} . ' ' . $msg . "\n";
   close $ircgate;
}

sub measure {
   my $time = shift || $begintime;

   return tv_interval($time);
}

sub mkuniqid {
   my $uniqid;
   my @chars = (48..57, 65..90, 97..122);

   newid: $uniqid .= chr($chars[rand($#chars)]) for 1..8;

   while (@{$dbh->selectcol_arrayref("SELECT uniqid FROM $sql{table} where uniqid = ?", {}, $uniqid)}) {
      goto newid;
   }

   return $uniqid;
}

sub mysql_connect {
   $dbh = DBI->connect("DBI:mysql:$sql{db}:$sql{host}", $sql{user}, $sql{pass},
          {RaiseError => 1, mysql_auto_reconnect => 1, mysql_enable_utf8 => 1});
}

sub mysql_disconnect {
   $dbh->disconnect if ($dbh);
}

sub pairwise_walk(&@) {
   my ($code, $prev) = (shift, shift);
   my @ret;

   push(@ret, $prev);

   for(@_) {
      push(@ret, $code->(local ($a, $b) = ($prev, $_)));
      $prev = $_;
   }

   return @ret;
}

sub print_header {
   my $what   = shift || 0; # 0 normal, 1 set cookie, 2 rss
   my $status = shift || 200;

   if ($what == 2) {
      print header(
         -status  => $status,
         -type    => 'application/rss+xml',
         -charset => 'utf-8',
      );
   }
   elsif ($what == 1 && $post) {
      print header(
         -status  => $status,
         -charset => 'utf-8',
         -cookie  => $cookie,
      );
   }
   else {
      print header(
         -status  => $status,
         -charset => 'utf-8',
      );
   }
}

sub print_page {
   my ($name, $title, $addvars, $setcookie, $status) = @_;

   $setcookie = 0   unless ($setcookie);
   $status    = 200 unless ($status);
   
   die("print_page($name): template $name.tt does not exist!") unless (-e "$ttopts{INCLUDE_PATH}$name.tt");

   my $ttvars = {
      measure   => \&measure,
      title     => $title . $vars{titleappend},
      totalhuds => $totalhuds,
      url       => $vars{url},
   };
   $$ttvars{$_} = $$addvars{$_} for (keys(%$addvars));

   if (exists $$ttvars{huds}) {
      for (keys($$ttvars{huds})) {
         if ($$ttvars{huds}{$_}{description}) {
            $$ttvars{huds}{$_}{description} = encode_entities($$ttvars{huds}{$_}{description});
            $$ttvars{huds}{$_}{description} =~ s!\b((?:[hH][tT][tT][pP][sS]?://|[wW][wW][wW]\.)[^\s)'"]+)!<a style="font-weight:normal;" href="$1">$1</a>!g;
           #$$ttvars{huds}{$_}{description} =~ s/\s+/<br />/g;
            $$ttvars{huds}{$_}{description} =~ s/\s/ /g;
         }
         else {
            $$ttvars{huds}{$_}{description} = '-';
         }
      }
   }

   #use Data::Dumper;
   #$$ttvars{debug} = Dumper($ttvars);

   if ($name eq 'rss') {
      print_header(2, $status);
   }
   elsif ($setcookie == 1) {
      print_header(1, $status);
   }
   else {
      print_header(0, $status);
   }
   $tt->process("$name.tt", $ttvars) || die($tt->error);
}

sub redir {
   my ($dest, $setcookie, $status) = @_;

   if ($setcookie) {
      print redirect(
         -uri    => $dest,
         -status => $status ? $status : 301,
         -cookie => $cookie,
      );
   }
   else {
      print redirect(
         -uri    => $dest,
         -status => $status ? $status : 301,
      );
   }
}

### pages

sub page_about {
   print_page('about', 'About Custom HUDs for Quake Live', {});
}

sub page_authors {
   my %authors;
   $authors{@$_[0]} = @$_[1] for (@{$dbh->selectall_arrayref("SELECT author, COUNT(*) FROM $sql{table} GROUP BY author")});

   my $cloud = HTML::TagCloud->new(levels => 42);
   $cloud->add($_, $vars{url} . '/author/' . $_, $authors{$_}) for (keys(%authors));

   my $myvars = {
      html => $cloud->html,
      css  => $cloud->css,
   };

   print_page('authors', 'Browse custom HUDs by author', $myvars);
}

sub page_download {
   if ($quniqid) {
      my $result = $dbh->selectrow_arrayref("SELECT author FROM $sql{table} WHERE BINARY uniqid = ?", {}, $quniqid);

      if (@$result) {
         redir($vars{url} . '/files/huds/' . @$result[0] . '_' . $quniqid . '.zip', 0, 302);

         my $result = $dbh->selectrow_arrayref("SELECT ip from $sql{sesstable} WHERE ip = ? AND uniqid = ? AND type = 'downloads'", {}, ($ip, $quniqid));

         unless ($result) {
            $dbh->do("UPDATE $sql{table} SET downloads=downloads+1 WHERE uniqid = ?", {}, $quniqid);
            $dbh->do("INSERT INTO $sql{sesstable} (ip, uniqid, type) VALUES (?, ?, 'downloads')", {}, $ip, $quniqid);
         }
      }
      else {
         page_info('Error', "HUD with ID '$quniqid' not found.", 404);
      }
   }
   else {
      redir($vars{url});
   }
}

sub page_info {
   my $myvars = {
      heading => shift,
      text    => shift,
   };

   my $status = shift;
   my $title  = $status ? '404' : 'Information';

   print_page('info', $title, $myvars, 0, $status);
}

sub page_index {
   if ($post) {
      redir($vars{url} . '/' . $qpage, 1, 303);
      return;
   }

   my $myvars = {
      num            => $qnum,
      page           => $qpage,
      maxhudsperpage => $vars{maxhudsperpage},
      sort           => $qsort,
   };

   my $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} ORDER BY $qsort DESC LIMIT ?, ?", 'id', {}, (($qnum*($qpage-1)), $qnum));

   if (%$result) {
      $$myvars{huds} = $result;
   }
   else {
      page_info('Error', 'No such page!', 404);
      return;
   }

   $$myvars{hudcount}  = scalar keys($$myvars{huds});
   $$myvars{pagecount} = ceil($totalhuds/$qnum);

   my $pageplusminus = 3;
   my @pages         = (1..$pageplusminus, $qpage-$pageplusminus..$qpage+$pageplusminus, ($$myvars{pagecount}+1)-$pageplusminus..$$myvars{pagecount});
   @pages = sort{ $a <=> $b } keys %{{ map { $_ => 1 } @pages }};

   while ($pages[0] < 1) {
      shift(@pages);
   }

   while ($pages[$#pages] > $$myvars{pagecount}) {
      pop(@pages);
   }

   @pages = pairwise_walk { $a+1 == $b ? $b : ('..', $b) } @pages;

   $$myvars{pages} = \@pages;

   print_page('index', "Page $qpage - Browse", $myvars, 1);
}

sub page_random {
   my $myvars;

   my $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} ORDER BY RAND() DESC LIMIT ?", 'id', {}, $vars{defhudsperpage});
   $$myvars{huds} = $result;

   print_page('random', 'Random custom HUDs', $myvars);
}

sub page_rss {
   my $myvars = {
      defhudsrss => $vars{defhudsrss},
   };

   my $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} ORDER BY id DESC LIMIT ?", 'id', {}, $vars{defhudsrss});
   $$myvars{huds} = $result;

   print_page('rss', 'RSS Feed', $myvars);
}

sub page_search {
   my ($myvars, $result);

   unless ($qauthor || $qdescription) {
      print_page('search', 'Find a custom HUD', {});
   }
   elsif ($qexact && $qauthor) {
      $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} WHERE author = ? ORDER BY id DESC", 'id', {}, $qauthor);
      $$myvars{huds} = $result;

      print_page('searchresults', "Author: $qauthor", $myvars);
   }
   else {
      my $authoranddesc;

      if ($qdescription) {
         if (length($qdescription) < 2) {
            page_info('Error', 'Please specify two (2) or more characters in the author or description search fields.');
            return;
         }

         if ($qauthor) {
            $authoranddesc = 1;
         }
         else {
            $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} WHERE description LIKE ? ORDER BY id DESC LIMIT ?", 'id', {}, ("%$qdescription%", $vars{maxhudspersearch}));
         }
      }
      elsif ($qauthor) {
         if (length($qauthor) < 2) {
            page_info('Error', 'Please specify two (2) or more characters in the author or description search fields.');
            return;
         }

         if ($qdescription) {
            $authoranddesc = 1;
         }
         else {
            $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} WHERE author LIKE ? ORDER BY id DESC LIMIT ?", 'id', {}, ("%$qauthor%", $vars{maxhudspersearch}));
         }
      }

      if ($authoranddesc) {
         $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} WHERE author LIKE ? AND description LIKE ? ORDER BY id DESC LIMIT ?", 'id', {}, ("%$qauthor%", "%$qdescription%", $vars{maxhudspersearch}));
      }

      $$myvars{huds} = $result;
      
      print_page('searchresults', 'Browse', $myvars);
   }
}

sub page_uniqid {
   my $myvars;

   my $result = $dbh->selectall_hashref("SELECT $sql{defhud} FROM $sql{table} WHERE BINARY uniqid = ?", 'uniqid', {}, $quniqid);
   $$myvars{huds}{$quniqid} = $$result{$quniqid};

   if (%$result) {
      print_page('uniqid', "HUD ID $quniqid by $$myvars{huds}{$quniqid}{author}", $myvars);

      my $result = $dbh->selectrow_arrayref("SELECT ip from $sql{sesstable} WHERE ip = ? AND uniqid = ? AND type = 'clicks'", {}, ($ip, $quniqid));

      unless ($result) {
         $dbh->do("UPDATE $sql{table} SET clicks=clicks+1 WHERE uniqid = ?", {}, $quniqid);
         $dbh->do("INSERT INTO $sql{sesstable} (ip, uniqid, type) VALUES (?, ?, 'clicks')", {}, $ip, $quniqid);
      }
   }
   else {
      page_info('Error', "HUD with ID '$quniqid' not found.", 404);
   }
}

sub page_upload {
   my $myvars = shift || {};

   print_page('upload', 'Upload a custom HUD', $myvars);
}

sub page_upload_post {
   if ($qauthor) {
      $qauthor =~ s/\s+/_/g;
      $qauthor =~ s/[^A-Za-z0-9-_]//g;
   }

   my $myvars = {
      author      => $qauthor,
      description => $qdescription,
   };
   
   if (!$qauthor) {
      $$myvars{reason} = 'Author name missing, please specify it:';
   }
   elsif (length($qauthor) > 31) {
      $$myvars{reason} = 'Author name is longer than 31 characters, please shorten it:';
   }
   elsif (length($qdescription) > 1000) {
      $$myvars{reason} = 'Description is longer than 1000 characters, please shorten it:';
   }
   elsif (!$qscreenshot) {
      $$myvars{reason} = 'Screenshot is missing!';
   }
   elsif ($qscreenshot !~ /\.(?:jpe?g|png)$/i) {
      $$myvars{reason} = 'Screenshot has the wrong file extension, it must be one of .jpg, .jpeg or .png!';
   }
   elsif (!$qhud) {
      $$myvars{reason} = 'HUD archive is missing!';
   }
   elsif ($qhud !~ /\.zip$/i) {
      $$myvars{reason} = 'HUD archive has the wrong file extension, it must be .zip!';
   }
   else {
      my $uniqid         = mkuniqid();
      my $filename       = $qauthor . '_' . $uniqid;
      my $hud            = $vars{huddir}        . '/' . $filename . '.zip';
      my $screenshot     = $vars{screenshotdir} . '/' . $filename . '.jpg';
      my $screenshottemp = $vars{tempdir}       . '/' . $filename . '.jpg';

      if (-e ($hud || $screenshot)) {
         $$myvars{reason} = 'HUD or screenshot already exist on the server!',
         page_upload($myvars);
         return;
      }

      unless (open my $fh, '>', $hud) {
         $$myvars{reason} = 'Could not write HUD!';
         page_upload($myvars);
         return;
      }
      else {
         binmode $fh;
         my $buffer;
         while (read $qhud, $buffer, 1024) {
            print $fh $buffer;
         }
         close $fh;
      }
      
      unless (chmod(0664, $hud)) {
         $$myvars{reason} = 'Chmod failed (HUD)!';
         page_upload($myvars);
         unlink $hud;
         return;
      }

      my $ft = File::Type->new;

      unless ($ft->checktype_filename($hud) eq 'application/zip') {
         $$myvars{reason} = 'HUD archive is not in ZIP format!';
         page_upload($myvars);
         unlink $hud;
         return;
      }

      unlink $vars{tempdir}       unless (-d $vars{tempdir});
      mkdir  $vars{tempdir}, 0700 unless (-e $vars{tempdir});

      unless (open my $fh, '>', $screenshottemp) {
         $$myvars{reason} = 'Could not write screenshot to tempdir!';
         page_upload($myvars);
         unlink $hud;
         return;
      }
      else {
         binmode $fh;
         my $buffer;
         while (read $qscreenshot, $buffer, 1024) {
            print $fh $buffer;
         }
         close $fh;
      }

      unless ($ft->checktype_filename($screenshottemp) ~~ [qw(image/jpeg image/png image/x-png)]) {
         $$myvars{reason} = 'Screenshot is not in JPG or PNG format!';
         page_upload($myvars);
         unlink $hud;
         unlink $screenshottemp;
         return;
      }

      my $rimg;
      unless ($rimg = Imager->new(file => $screenshottemp)) {
            $$myvars{reason} = 'Could not open temporary screenshot for reading';
            page_upload($myvars);
            unlink $hud;
            unlink $screenshottemp;
            return;
      }

      my ($rimgx, $rimgy) = ($rimg->getwidth, $rimg->getheight);
      my ($wimgx, $wimgy) = ($rimgx, $rimgy);
      my ($max, $res)     = (640, undef);

      $res = ($rimgx > $rimgy) ? ($rimgx/$max) : ($rimgy/$max);

      if ($res != 0) {
         $wimgx = int($rimgx/$res);
         $wimgy = int($rimgy/$res);
      }

      my $wimg = $rimg->scale(xpixels => $wimgx, ypixels => $wimgy);
      $$myvars{imgy} = $wimgy;

      unless ($wimg->write(file => $screenshot, type => 'jpeg',  jpegquality => 95)) {
         $$myvars{reason} = 'Could not write screenshot to destination!';
         page_upload($myvars);
         unlink $hud;
         unlink $screenshottemp;
         return;
      }

      unless (chmod(0664, $screenshot)) {
         $$myvars{reason} = 'Chmod failed (screenshot)!';
         page_upload($myvars);
         unlink $hud;
         unlink $screenshot;
         return;
      }

      unless($dbh->do("INSERT INTO $sql{table} (author, description, ip, timestamp, uniqid, imgy) VALUES(?, ?, ?, now(), ?, ?)", {}, ($qauthor, $qdescription, $ip, $uniqid, $wimgy))) {
         unlink $hud;
         unlink $screenshottemp;
         unlink $screenshot;
         page_upload($myvars);
         return;
      }

      redir($vars{url} . '/hud/' . $uniqid, 0, 303);

      unlink $screenshottemp;

      irc('[qlhud] ' . $qauthor . ' :: ' . $vars{url} . '/hud/' . $uniqid);

      return;
   }

   page_upload($myvars);
}
