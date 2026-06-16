/*
Query 13: Roaming data usage by roaming destination.

Output columns:
- service_type
- charge_type
- country
- usage_mbs
*/

const roamingDestinationLabelById = {
  4: "Greece-Vodafone",
  5: "Netherlands-Vodafone",
  8: "France-Bouygues Telecom",
  9: "Spain-Vodafone",
  10: "Hungary-Vodafone",
  11: "Italy-Vodafone",
  12: "Italy-H3G",
  13: "Romania-Vodafone",
  14: "Switzerland-Swisscom",
  15: "CzechRepublic-Vodafone",
  16: "Austria-H3G",
  17: "UK-Vodafone",
  18: "UK-H3G",
  19: "Denmark-H3G",
  20: "Sweden-H3G",
  21: "Russian Federation-BeeLine/VimpelCom",
  22: "Germany-Vodafone",
  23: "Portugal-Vodafone",
  24: "Ireland-Vodafone",
  25: "Ireland-H3G",
  26: "Albania-Vodafone",
  27: "Malta-Vodafone",
  30: "Turkey-Vodafone-Telsim",
  33: "Canada-Rogers",
  34: "United States-T-Mobile",
  35: "Guam-DoCoMoPacific",
  37: "United States-ATT",
  40: "Myanmar-MPT",
  43: "SaudiArabia-STC",
  46: "UAE-Du",
  48: "Israel-Partner",
  49: "Israel-Pelephone",
  51: "Qatar-Vodafone",
  56: "Japan-NTTDoCoMo",
  59: "Korea-SKT",
  60: "Korea-KT Freetel Co. Ltd.",
  62: "Vitenam-Vitenam Mobile",
  64: "HongKong-H3G",
  72: "Macau-H3G",
  74: "Cambodia-Smart",
  75: "Laos-Lao Telecom",
  79: "China-ChinaMobile",
  81: "China-Unicom",
  82: "Taiwan-FET",
  83: "Taiwan-Chunghwa",
  87: "Malaysia-Mi3G-UMobile",
  89: "Malaysia-Celcom",
  92: "Australia-Vodafone",
  93: "Indonesia-Indosat",
  97: "Philippines-Smart",
  99: "Thailand-AIS",
  103: "Singapore-Starhub",
  105: "NewZealand-Vodafone",
  107: "Egypt-Orange",
  111: "Ghana-Vodafone",
  113: "CongoDR-Vodafone",
  116: "Tanzania-Vodafone",
  117: "Mozambique-Vodafone",
  118: "Lesotho-Vodafone",
  119: "SouthAfrica-Vodafone",
  120: "Peru-Telefonica",
  121: "Argentina-Telefonica",
  122: "Argentina-Personal",
  123: "Brazil-Telefonica",
  124: "Chile-Telefonica",
  125: "Colombia-Telefonica",
  126: "Ecuador-Telefonica",
  127: "Uruguay-Telefonica",
  131: "Taiwan-Taiwan Mobile",
  135: "HongKong-SIP CLIENT",
  435: "HongKong-HKCSL",
  436: "HongKong-Smartone",
  437: "HongKong-CMHK",
  501: "Indonesia-Hutchison 3",
  502: "Indonesia-Telkomsel",
  503: "Japan-Softbank",
  504: "Philippines-Globe Telecom",
  505: "Singapore-M1",
  506: "Singapore-Simba",
  507: "Singapore-SingTel",
  508: "Thailand-DTAC",
  509: "Thailand-TOT",
  510: "Thailand-Truemove",
  511: "Australia-Optus",
  512: "Azerbaijan-Bakcell",
  513: "Bahrain-STC",
  514: "Bangladesh-Grameenphone",
  515: "Bangladesh-Banglalink",
  516: "Belgium-Orange/Mobistar",
  517: "Brunei-UNN/DST/Progresif",
  518: "Cambodia-Cellcard/Mobitel",
  519: "Cambodia-Metfone",
  520: "Canada-Bell",
  521: "Canada-Telus",
  522: "Costa Rica-Telefonica Latam",
  523: "Croatia-Hrvatski Telekom/T-Mobile",
  524: "Denmark-Telenor",
  525: "Egypt-Vodafone",
  526: "El Salvador-Telefonica Latam",
  527: "Finland-DNA",
  528: "France-Free Mobile",
  529: "France-Orange",
  530: "Germany-O2",
  531: "Greece-WIND/TIM",
  532: "Iceland-Nova",
  533: "India-Airtel",
  534: "India-Airtel",
  535: "India-Reliance Jio",
  536: "Ireland-EIR/Meteor",
  537: "Italy-Iliad",
  538: "Kazakhstan-Beeline/Kar-Tel LLP",
  539: "Laos-Unitel",
  540: "Latvia-Bite (SIA Bite)",
  541: "Lithuania-Bite",
  542: "Luxembourg-Orange",
  543: "Macau-CTM",
  544: "Mexico-Movistar",
  545: "Moldova-Orange",
  546: "Mongolia-MobiCom",
  547: "Montenegro-Mtel",
  548: "Myanmar-Mytel",
  549: "Myanmar-Telenor",
  550: "Nepal-Nepal Telecom",
  551: "NewZealand-Spark",
  552: "Norway-Telenor",
  553: "Oman-VF Oman",
  554: "Pakistan-Telenor",
  555: "Poland-Orange",
  556: "Poland-Play",
  557: "Poland-Plus / Polkomtel",
  558: "Romania-Telekom",
  559: "Romania-Orange",
  560: "SaudiArabia-Zain / MTC",
  561: "SaudiArabia-Mobily",
  562: "Slovakia-Telekom",
  563: "Spain-Orange",
  564: "Spain-Movistar / Telefonica Espania",
  565: "SRI LANKA-Hutchison 3",
  566: "SRI LANKA-Mobitel",
  567: "Sweden-Telenor",
  568: "Switzerland-Salt / Orange Communications SA",
  569: "Switzerland-Sunrise",
  570: "Timor-Leste-Telemor",
  571: "UAE-E&",
  572: "UK-O2",
  573: "Ukraine-Lifecell / Astelit",
  574: "Ukraine-Vodafone",
  575: "Uzbekistan-Uzbektelecom",
  576: "Venezuela-Telefonica Latam",
  577: "Vitenam-Vietnam: Viettel"
};

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: { $in: ["4G", "5G"] },
      roaming_destination_id: { $ne: 87 },
      rating_group: { $nin: ["500003"] }
    }
  },
  {
    $group: {
      _id: "$roaming_destination_id",
      usage_mbs: {
        $sum: {
          $round: [
            {
              $divide: [
                { $toDouble: { $ifNull: ["$act_update_used_volume", 0] } },
                1048576
              ]
            },
            2
          ]
        }
      }
    }
  },
  {
    $addFields: {
      country: {
        $function: {
          body: function (destinationId, labelMap) {
            const key = String(destinationId);
            return labelMap[key] || "Unknown";
          },
          args: ["$_id", roamingDestinationLabelById],
          lang: "js"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Data Roaming" },
      charge_type: { $literal: "MO" },
      country: 1,
      usage_mbs: 1
    }
  },
  {
    $sort: {
      country: 1
    }
  }
]);
