/*
Query 11: International SMS by destination country.

Equivalent PostgreSQL query:

SELECT
    'SMS' AS service_type,
    'SMS MO' AS charge_type,
    COALESCE(cc.country, 'UNMAPPED') AS country,
    COUNT(*) AS sms_count
FROM iot_portal_tb_usage_log t
LEFT JOIN LATERAL (
    SELECT c.country
    FROM country_code c
    WHERE TRIM(t.opposite_number::text) LIKE c.country_code || '%'
    ORDER BY LENGTH(c.country_code) DESC
    LIMIT 1
) cc ON TRUE
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0
  AND t.opposite_number IS NOT NULL
  AND BTRIM(t.opposite_number::text) NOT IN ('', 'None', 'none')
  AND BTRIM(t.opposite_number::text) NOT LIKE '60%'
GROUP BY COALESCE(cc.country, 'UNMAPPED')
ORDER BY country;

Output columns:
- service_type
- charge_type
- country
- sms_count

Included records:
- usage_logs records within the reporting window using usage_start_time
- rat_type = 'SM'
- roaming_destination_id = 87
- act_usage_unit > 0
- opposite_number present and not starting with '60'

service_type_sub_cd = 'MO' is not required as 'MO' and 'MT' are only applicable for rat_type = 'VO' as of now, but if in future there are 'MO' and 'MT' for 'SM', we can easily add that filter back without affecting existing data since we are only looking at 'SM' records here.

Fixed/hardcoded Output values:
- service_type = 'SMS'
- charge_type = 'SMS MO'

Country is derived from the country_code collection using longest-prefix
matching on opposite_number.
*/

db.{{usage_log}}.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "SM",
      roaming_destination_id: 87,
      act_usage_unit: { $gt: 0 },
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
      opposite_number_digits: {
        $nin: ["", "None", "none"]
      }
    }
  },
  {
    $match: {
      opposite_number_digits: { $not: { $regex: "^60" } }
    }
  },
  {
    $lookup: {
      from: "{{country_code}}",
      let: {
        destination_number: "$opposite_number_digits"
      },
      pipeline: [
        {
          $project: {
            _id: 0,
            country: 1,
            country_code_str: { $toString: "$country_code" },
            code_length: { $strLenCP: { $toString: "$country_code" } }
          }
        },
        {
          $match: {
            $expr: {
              $regexMatch: {
                input: "$$destination_number",
                regex: { $concat: ["^", "$country_code_str"] }
              }
            }
          }
        },
        {
          $sort: {
            code_length: -1
          }
        },
        {
          $limit: 1
        }
      ],
      as: "country_match"
    }
  },
  {
    $addFields: {
      country: { $ifNull: [{ $arrayElemAt: ["$country_match.country", 0] }, "UNMAPPED"] }
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
