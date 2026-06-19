/*
Query: Roaming data usage by country.

Equivalent PostgreSQL query:

SELECT
    'Data Roaming' AS service_type,
    'MO' AS charge_type,
    COALESCE(
        REPLACE(REPLACE(rd.roaming_destination_name, ': ', '-'), ':', '-'),
        rd.country,
        'UNMAPPED'
    ) AS country,
    ROUND(SUM(COALESCE(t.act_usage_unit, 0)) / 1048576.0, 2) AS usage_mbs
FROM iot_portal_tb_usage_log t
LEFT JOIN roaming_destination rd
    ON rd.roaming_destination_id = t.roaming_destination_id
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type IN ('4G', '5G')
  AND t.roaming_destination_id <> 87
  AND COALESCE(t.act_usage_unit, 0) > 0
  -- rating_group 500003 is used for MCMC/MERC999 data.
  -- Not filtering it out for now.
GROUP BY
    COALESCE(
        REPLACE(REPLACE(rd.roaming_destination_name, ': ', '-'), ':', '-'),
        rd.country,
        'UNMAPPED'
    )
ORDER BY country;

Output columns:
- service_type
- charge_type
- country
- usage_mbs

Included records:
- usage_logs records within the reporting window using usage_start_time
- rat_type IN ('4G', '5G')
- roaming_destination_id != 87
- act_usage_unit > 0

Output values:
- service_type = 'Data Roaming'
- charge_type = 'MO'

Country is derived from the roaming_destination collection.
If roaming_destination_name exists it is normalized to Country-Network by
replacing ':' or ': ' with '-'. If not, the country field is used.
If neither exists, the row is labeled UNMAPPED or UNMAPPED-<id>.

rating_group 500003 is used for MCMC/MERC999 data.
It is not filtered out in this query.
*/

db.{{usage_log}}.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: { $in: ["4G", "5G"] },
      roaming_destination_id: { $ne: 87 },
      act_usage_unit: { $gt: 0 },
      // rating_group 500003 is used for MCMC/MERC999 data.
      // Not filtering it out for now.
      // rating_group: { $nin: ["500003"] }
    }
  },
  {
    $lookup: {
      from: "{{roaming_destination}}",
      localField: "roaming_destination_id",
      foreignField: "roaming_destination_id",
      as: "destination_ref"
    }
  },
  {
    $addFields: {
      destination_ref: { $arrayElemAt: ["$destination_ref", 0] }
    }
  },
  {
    $addFields: {
      normalized_destination_name: {
        $replaceAll: {
          input: {
            $replaceAll: {
              input: {
                $trim: {
                  input: { $ifNull: ["$destination_ref.roaming_destination_name", ""] }
                }
              },
              find: ": ",
              replacement: "-"
            }
          },
          find: ":",
          replacement: "-"
        }
      },
      normalized_country: {
        $trim: {
          input: { $ifNull: ["$destination_ref.country", ""] }
        }
      }
    }
  },
  {
    $addFields: {
      country: {
        $switch: {
          branches: [
            {
              case: { $ne: ["$normalized_destination_name", ""] },
              then: "$normalized_destination_name"
            },
            {
              case: { $ne: ["$normalized_country", ""] },
              then: "$normalized_country"
            }
          ],
          default: {
            $cond: [
              { $ne: ["$roaming_destination_id", null] },
              { $concat: ["UNMAPPED-", { $toString: "$roaming_destination_id" }] },
              "UNMAPPED"
            ]
          }
        }
      }
    }
  },
  {
    $group: {
      _id: "$country",
      usage_mbs: {
        $sum: {
          $divide: [
            { $toDouble: { $ifNull: ["$act_usage_unit", 0] } },
            1048576
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Data Roaming" },
      charge_type: { $literal: "MO" },
      country: "$_id",
      usage_mbs: { $round: ["$usage_mbs", 2] }
    }
  },
  {
    $sort: {
      country: 1
    }
  }
]);
