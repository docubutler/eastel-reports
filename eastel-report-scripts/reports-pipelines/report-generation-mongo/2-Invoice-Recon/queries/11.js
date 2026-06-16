/*
Query 11: International SMS by destination country.

Output columns:
- service_type
- charge_type
- country
- sms_count
*/

const countryCodeMappings = [
  ["1246", "Barbados"], ["1758", "Saint Lucia"], ["1767", "Dominica"], ["1787", "Puerto Rico"],
  ["1809", "Dominican Republic"], ["1829", "Dominican Republic"], ["1849", "Dominican Republic"],
  ["1868", "Trinidad & Tobago"], ["1869", "Saint Kitts and Nevis"], ["1876", "Jamaica"],
  ["1939", "Puerto Rico"], ["211", "South Sudan"], ["212", "Morocco"], ["213", "Algeria"],
  ["216", "Tunisia"], ["218", "Libya"], ["220", "Gambia"], ["221", "Senegal"], ["222", "Mauritania"],
  ["223", "Mali"], ["224", "Guinea Republic"], ["225", "Ivory Coast"], ["226", "Burkina Faso"],
  ["227", "Niger"], ["228", "Togo"], ["230", "Mauritius"], ["231", "Liberia"], ["233", "Ghana"],
  ["234", "Nigeria"], ["235", "Chad"], ["237", "Cameroon"], ["238", "Cape Verde"],
  ["240", "Equatorial Guinea"], ["242", "Congo Brazaville"], ["243", "DR Congo"], ["244", "Angola"],
  ["249", "Sudan"], ["250", "Rwanda"], ["251", "Ethiopia"], ["252", "Somalia"], ["253", "Djibouti"],
  ["254", "Kenya"], ["255", "Tanzania"], ["256", "Uganda"], ["258", "Mozambique"], ["260", "Zambia"],
  ["261", "Madagascar"], ["262", "Reunion Island"], ["263", "Zimbabwe"], ["264", "Namibia"],
  ["265", "Malawi"], ["267", "Botswana"], ["268", "Swaziland"], ["269", "Comoros"], ["291", "Eritrea"],
  ["350", "Gibraltar"], ["351", "Portugal"], ["352", "Luxembourg"], ["353", "Ireland"],
  ["354", "Iceland"], ["355", "Albania"], ["356", "Malta"], ["357", "Cyprus"], ["358", "Finland"],
  ["359", "Bulgaria"], ["370", "Lithuania"], ["371", "Latvia"], ["372", "Estonia"], ["373", "Moldova"],
  ["374", "Armenia"], ["375", "Belarus"], ["378", "San Marino"], ["380", "Ukraine"], ["381", "Serbia"],
  ["382", "Montenegro"], ["385", "Croatia"], ["386", "Slovenia"], ["387", "Bosnia"], ["389", "Macedonia"],
  ["420", "Czech Republic"], ["421", "Slovakia"], ["423", "Liechtenstein"], ["501", "Belize"],
  ["502", "Guatemala"], ["503", "El Salvador"], ["504", "Honduras"], ["505", "Nicaragua"],
  ["506", "Costa Rica"], ["507", "Panama"], ["591", "Bolivia"], ["592", "Guyana"], ["593", "Ecuador"],
  ["595", "Paraguay"], ["597", "Suriname"], ["598", "Uruguay"], ["670", "Timor-Leste"], ["673", "Brunei"],
  ["675", "Papua New Guinea"], ["679", "Fiji"], ["685", "Western Samoa"], ["686", "Kiribati"],
  ["687", "New Caledonia"], ["690", "Tokelau"], ["850", "North Korea"], ["852", "Hong Kong"],
  ["853", "Macau"], ["855", "Cambodia"], ["856", "Laos"], ["870", "Inmarsat SATELLITE"],
  ["880", "Bangladesh"], ["881", "Global MOBILE Satelllite"], ["882", "International Networks SATELLITE"],
  ["883", "International Networks SATELLITE"], ["886", "Taiwan"], ["960", "Maldives"], ["961", "Lebanon"],
  ["962", "Jordan"], ["963", "Syria"], ["964", "Iraq"], ["965", "Kuwait"], ["966", "Saudi Arabia"],
  ["967", "Yemen"], ["968", "Oman"], ["970", "Palestine"], ["971", "United Arab Emirates"],
  ["972", "Israel"], ["973", "Bahrain"], ["974", "Qatar"], ["975", "Bhutan"], ["976", "Mongolia"],
  ["977", "Nepal"], ["992", "Tajikistan"], ["993", "Turkmenistan"], ["994", "Azerbaijan"],
  ["995", "Georgia"], ["996", "Kyrghyzstan"], ["998", "Uzbekistan"], ["20", "Egypt"],
  ["27", "South Africa"], ["30", "Greece"], ["31", "Netherlands"], ["32", "Belgium"],
  ["33", "France"], ["34", "Spain"], ["36", "Hungary"], ["39", "Italy"], ["40", "Romania"],
  ["41", "Switzerland"], ["43", "Austria"], ["44", "United Kingdom"], ["45", "Denmark"],
  ["46", "Sweden"], ["47", "Norway"], ["48", "Poland"], ["49", "Germany"], ["51", "Peru"],
  ["52", "Mexico"], ["54", "Argentina"], ["55", "Brazil"], ["56", "Chile"], ["57", "Colombia"],
  ["58", "Venezuela"], ["60", "Malaysia"], ["61", "Australia"], ["62", "Indonesia"],
  ["63", "Philippines"], ["64", "New Zealand"], ["65", "Singapore"], ["66", "Thailand"],
  ["81", "Japan"], ["82", "South Korea"], ["84", "Vietnam"], ["86", "China"], ["90", "Turkey"],
  ["91", "India"], ["92", "Pakistan"], ["93", "Afghanistan"], ["94", "Sri Lanka"], ["95", "Myanmar"],
  ["98", "Iran"], ["1", "United States/Canada"], ["7", "Russia/Kazakhstan"]
];

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "SM",
      service_type_sub_cd: "MO",
      roaming_destination_id: 87,
      opposite_number: { $exists: true, $ne: null }
    }
  },
  {
    $addFields: {
      opposite_number_digits: {
        $trim: {
          input: { $toString: "$opposite_number" }
        }
      }
    }
  },
  {
    $match: {
      opposite_number_digits: { $not: { $regex: "^60" } }
    }
  },
  {
    $addFields: {
      country: {
        $function: {
          body: function (msisdn, mappings) {
            if (!msisdn) {
              return "Unknown";
            }
            for (const [code, country] of mappings) {
              if (msisdn.startsWith(code)) {
                return country;
              }
            }
            return "Unknown";
          },
          args: ["$opposite_number_digits", countryCodeMappings],
          lang: "js"
        }
      }
    }
  },
  {
    $group: {
      _id: "$country",
      sms_count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "SMS" },
      charge_type: { $literal: "SMS MO" },
      country: "$_id",
      sms_count: 1
    }
  },
  {
    $sort: {
      country: 1
    }
  }
]);
